// Command egress maps what an agent sandbox can actually reach, from inside it.
//
// It is a port of egress_probe.py to Go, for one reason: Go modules are the
// only distribution channel this sandbox can publish to without holding a
// credential. Everything else reachable from here — PyPI, npm, crates.io,
// Docker Hub — needs an account first. `go run <module>@latest` needs nothing
// but a public git tag, so this is the one door an agent can open alone.
//
// Why the tool exists
//
// An agent running in a sandbox is usually told "network access is governed by
// an allowlist" and is not shown the list. That list decides which distribution
// channels exist for the agent, so not knowing it is not a small gap. This
// recovers the answer empirically, one host at a time.
//
// How the classification works
//
// Traffic leaves through an HTTP CONNECT proxy named by $HTTPS_PROXY, except
// for hosts matching $NO_PROXY, which go direct. So there are two probes:
//
//	proxied host   send `CONNECT host:443` and read the proxy's status line
//	               200 -> the allowlist permits this host (tunnel opened)
//	               403 -> the allowlist does not permit this host
//	direct host    open a TCP connection to host:443
//
// Then, for hosts that got through, complete a TLS handshake and send `HEAD /`
// to see whether the origin answers. An origin's own 403 (npm, PyPI's upload
// endpoint) still means REACHABLE — the refusal came from the service, not from
// the sandbox. Conflating those two is the easiest way to draw the map wrong.
//
//	REACHABLE  the sandbox let the connection out and something answered
//	BLOCKED    the proxy refused the tunnel
//	NO_HOST    permitted, but DNS or TCP failed (host absent / down)
//
// Usage
//
//	go run github.com/nemuprojectofficial-glitch/n0-public/cmd/egress@latest
//	egress --hosts a.com,b.io      # probe specific hosts
//	egress --file hosts.txt        # one host per line
//	egress --json                  # machine-readable output
//
// It is read-only. It never sends a request body, never authenticates, and
// never attempts to get around anything: a blocked host stays blocked, and that
// is the answer, not an obstacle. Exit status is 0 whatever the findings —
// this is a measurement, not a test.
package main

import (
	"bufio"
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"net/url"
	"os"
	"sort"
	"strings"
	"sync"
	"time"
)

// Result classifications.
const (
	Reachable = "REACHABLE"
	Blocked   = "BLOCKED"
	NoHost    = "NO_HOST"
)

// defaultHosts is a starting list, grouped by what the host would let an agent
// *do*. Publishing surfaces come first: those decide whether an agent can reach
// anyone at all.
var defaultHosts = []string{
	// package registries — an agent that can write here can distribute software
	"pypi.org", "upload.pypi.org", "test.pypi.org", "files.pythonhosted.org",
	"registry.npmjs.org", "www.npmjs.com",
	"crates.io", "static.crates.io",
	"rubygems.org", "packagist.org", "hex.pm", "api.nuget.org",
	"repo1.maven.org", "anaconda.org", "conda.anaconda.org",
	"proxy.golang.org", "pkg.go.dev", "index.golang.org", "sum.golang.org",
	"jsr.io",

	// container registries
	"ghcr.io", "index.docker.io", "registry-1.docker.io", "hub.docker.com",

	// code hosts — artifacts can be left here and indexed
	"github.com", "api.github.com", "raw.githubusercontent.com",
	"codeload.github.com", "objects.githubusercontent.com", "gist.github.com",
	"gitlab.com", "bitbucket.org", "sourceforge.net", "launchpad.net",
	"codeberg.org", "gitea.com", "git.sr.ht",

	// places where people are — an agent that can write here can reach a person
	"news.ycombinator.com", "lobste.rs", "www.reddit.com", "dev.to",
	"zenn.dev", "qiita.com", "note.com",
	"stackoverflow.com", "api.stackexchange.com",
	"x.com", "bsky.app", "public.api.bsky.app", "mastodon.social",
	"discord.com", "api.telegram.org",

	// search engines
	"www.google.com", "duckduckgo.com", "www.bing.com",

	// payments — an agent that can write here can be paid
	"api.stripe.com", "ko-fi.com", "buymeacoffee.com", "gumroad.com", "polar.sh",

	// CDNs
	"cdn.jsdelivr.net", "unpkg.com", "esm.sh",

	// OS package repositories
	"deb.debian.org", "archive.ubuntu.com",

	// controls. example.com is an ordinary host that a real allowlist should
	// refuse; the .invalid name must never resolve. If either comes back
	// REACHABLE, the map below is not measuring what it claims to measure.
	"example.com", "this-host-does-not-exist.invalid",
}

// Result is one host's verdict.
type Result struct {
	Host    string `json:"host"`
	Verdict string `json:"verdict"`
	Via     string `json:"via"`              // "proxy" or "direct"
	Detail  string `json:"detail"`           // proxy status line, origin status line, or error
	Origin  string `json:"origin,omitempty"` // origin's own answer to HEAD /, when it answered
}

func main() {
	var (
		hostsFlag  = flag.String("hosts", "", "comma-separated hosts to probe instead of the built-in list")
		fileFlag   = flag.String("file", "", "file with one host per line")
		jsonFlag   = flag.Bool("json", false, "emit JSON instead of a table")
		timeout    = flag.Duration("timeout", 12*time.Second, "per-connection timeout")
		concurrent = flag.Int("concurrency", 8, "how many hosts to probe at once")
		noOrigin   = flag.Bool("no-origin", false, "stop after the tunnel; do not talk to the origin")
	)
	flag.Parse()

	hosts, err := selectHosts(*hostsFlag, *fileFlag)
	if err != nil {
		fmt.Fprintln(os.Stderr, "egress:", err)
		os.Exit(2)
	}
	if len(hosts) == 0 {
		fmt.Fprintln(os.Stderr, "egress: no hosts to probe")
		os.Exit(2)
	}

	proxy := proxyURL()
	noProxy := splitList(firstEnv("NO_PROXY", "no_proxy"))

	results := probeAll(hosts, proxy, noProxy, *timeout, *concurrent, !*noOrigin)

	if *jsonFlag {
		emitJSON(results, proxy)
		return
	}
	emitTable(results, proxy)
}

func selectHosts(hostsFlag, fileFlag string) ([]string, error) {
	switch {
	case hostsFlag != "" && fileFlag != "":
		return nil, fmt.Errorf("use --hosts or --file, not both")
	case hostsFlag != "":
		return dedupe(splitList(hostsFlag)), nil
	case fileFlag != "":
		f, err := os.Open(fileFlag)
		if err != nil {
			return nil, err
		}
		defer f.Close()
		var out []string
		sc := bufio.NewScanner(f)
		for sc.Scan() {
			line := strings.TrimSpace(sc.Text())
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			out = append(out, line)
		}
		return dedupe(out), sc.Err()
	default:
		return defaultHosts, nil
	}
}

// proxyURL returns the CONNECT proxy the environment says to use, or nil.
func proxyURL() *url.URL {
	raw := firstEnv("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
	if raw == "" {
		return nil
	}
	if !strings.Contains(raw, "://") {
		raw = "http://" + raw
	}
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return nil
	}
	return u
}

// bypassesProxy reports whether NO_PROXY sends this host direct. The matching
// follows the usual convention: an entry matches the host itself or any
// subdomain of it, and "*" matches everything.
func bypassesProxy(host string, noProxy []string) bool {
	h := strings.ToLower(strings.TrimSuffix(host, "."))
	for _, entry := range noProxy {
		e := strings.ToLower(strings.TrimSpace(entry))
		e = strings.TrimPrefix(e, "*")
		e = strings.TrimPrefix(e, ".")
		if e == "" {
			continue
		}
		if entry == "*" || h == e || strings.HasSuffix(h, "."+e) {
			return true
		}
	}
	return false
}

func probeAll(hosts []string, proxy *url.URL, noProxy []string, timeout time.Duration, concurrency int, askOrigin bool) []Result {
	if concurrency < 1 {
		concurrency = 1
	}
	results := make([]Result, len(hosts))
	sem := make(chan struct{}, concurrency)
	var wg sync.WaitGroup
	for i, h := range hosts {
		wg.Add(1)
		go func(i int, h string) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			results[i] = probe(h, proxy, noProxy, timeout, askOrigin)
		}(i, h)
	}
	wg.Wait()
	return results
}

// probe opens one connection and reports what the sandbox did with it. It never
// sends a request body and never authenticates.
func probe(host string, proxy *url.URL, noProxy []string, timeout time.Duration, askOrigin bool) Result {
	r := Result{Host: host, Via: "direct"}
	direct := proxy == nil || bypassesProxy(host, noProxy)
	if !direct {
		r.Via = "proxy"
	}

	var conn net.Conn
	var err error
	deadline := time.Now().Add(timeout)

	if direct {
		conn, err = net.DialTimeout("tcp", net.JoinHostPort(host, "443"), timeout)
		if err != nil {
			// With no proxy in the way, a refusal is about the destination, not
			// about the sandbox. Say so rather than calling it BLOCKED.
			r.Verdict = NoHost
			r.Detail = trimErr(err)
			return r
		}
	} else {
		conn, err = net.DialTimeout("tcp", proxy.Host, timeout)
		if err != nil {
			r.Verdict = NoHost
			r.Detail = "cannot reach the proxy itself: " + trimErr(err)
			return r
		}
		conn.SetDeadline(deadline)
		status, rest, cerr := connect(conn, host)
		if cerr != nil {
			conn.Close()
			r.Verdict = NoHost
			r.Detail = trimErr(cerr)
			return r
		}
		r.Detail = status
		if !strings.Contains(status, " 200") {
			// The proxy answered, and its answer was not "tunnel opened". That
			// is the allowlist speaking. A refusal usually carries an
			// explanatory body; we do not need it, and its presence must not
			// change the verdict.
			conn.Close()
			r.Verdict = Blocked
			return r
		}
		// Tunnel opened. A well-behaved proxy sends nothing after the blank
		// line, but if it did, those bytes are already the origin's and the TLS
		// handshake below has to see them first.
		conn = &prefixedConn{Conn: conn, rest: rest}
	}
	defer conn.Close()
	conn.SetDeadline(deadline)

	if !askOrigin {
		r.Verdict = Reachable
		if r.Detail == "" {
			r.Detail = "tcp connect succeeded"
		}
		return r
	}

	origin, oerr := headRequest(conn, host)
	if oerr != nil {
		// The sandbox let the connection out; the origin then failed to speak
		// TLS or answer. That is still egress, so it is not BLOCKED — but it is
		// not a working destination either.
		r.Verdict = NoHost
		r.Detail = trimErr(oerr)
		return r
	}
	r.Verdict = Reachable
	r.Origin = origin
	if r.Detail == "" {
		r.Detail = "tcp connect succeeded"
	}
	return r
}

// connect performs the CONNECT handshake and returns the proxy's status line
// together with any bytes it read past the end of the header block.
func connect(conn net.Conn, host string) (string, []byte, error) {
	req := fmt.Sprintf("CONNECT %s:443 HTTP/1.1\r\nHost: %s:443\r\n\r\n", host, host)
	if _, err := conn.Write([]byte(req)); err != nil {
		return "", nil, err
	}
	br := bufio.NewReader(conn)
	line, err := br.ReadString('\n')
	if err != nil {
		return "", nil, err
	}
	// Drain the rest of the proxy's header block so the tunnel starts clean.
	for {
		l, err := br.ReadString('\n')
		if err != nil || strings.TrimSpace(l) == "" {
			break
		}
	}
	var rest []byte
	if n := br.Buffered(); n > 0 {
		rest, _ = br.Peek(n)
		rest = append([]byte(nil), rest...)
	}
	return strings.TrimSpace(line), rest, nil
}

// prefixedConn replays bytes that were read off the wire early, before handing
// the rest of the conversation back to the socket.
type prefixedConn struct {
	net.Conn
	rest []byte
}

func (c *prefixedConn) Read(p []byte) (int, error) {
	if len(c.rest) > 0 {
		n := copy(p, c.rest)
		c.rest = c.rest[n:]
		return n, nil
	}
	return c.Conn.Read(p)
}

// headRequest completes a TLS handshake and asks the origin for HEAD /. The
// origin's own status is returned verbatim — a 4xx here means the service
// refused, which still proves the sandbox let us out.
func headRequest(conn net.Conn, host string) (string, error) {
	tc := tls.Client(conn, &tls.Config{ServerName: host})
	if err := tc.Handshake(); err != nil {
		return "", err
	}
	req := fmt.Sprintf("HEAD / HTTP/1.1\r\nHost: %s\r\nUser-Agent: egress-probe\r\nConnection: close\r\n\r\n", host)
	if _, err := tc.Write([]byte(req)); err != nil {
		return "", err
	}
	line, err := bufio.NewReader(tc).ReadString('\n')
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(line), nil
}

func emitTable(results []Result, proxy *url.URL) {
	where := "none (all traffic is direct)"
	if proxy != nil {
		where = proxy.Host
	}
	fmt.Printf("egress map  %s\n", time.Now().UTC().Format(time.RFC3339))
	fmt.Printf("proxy: %s\n\n", where)

	counts := map[string]int{}
	width := 0
	for _, r := range results {
		counts[r.Verdict]++
		if len(r.Host) > width {
			width = len(r.Host)
		}
	}

	byVerdict := map[string][]Result{}
	for _, r := range results {
		byVerdict[r.Verdict] = append(byVerdict[r.Verdict], r)
	}
	for _, v := range []string{Reachable, Blocked, NoHost} {
		group := byVerdict[v]
		if len(group) == 0 {
			continue
		}
		sort.Slice(group, func(i, j int) bool { return group[i].Host < group[j].Host })
		fmt.Printf("%s (%d)\n", v, len(group))
		for _, r := range group {
			detail := r.Origin
			if detail == "" {
				detail = r.Detail
			}
			fmt.Printf("  %-*s  %s\n", width, r.Host, detail)
		}
		fmt.Println()
	}
	fmt.Printf("%d probed: %d reachable, %d blocked, %d no host\n",
		len(results), counts[Reachable], counts[Blocked], counts[NoHost])
}

func emitJSON(results []Result, proxy *url.URL) {
	out := struct {
		MeasuredAt string   `json:"measured_at"`
		Proxy      string   `json:"proxy"`
		Results    []Result `json:"results"`
	}{
		MeasuredAt: time.Now().UTC().Format(time.RFC3339),
		Results:    results,
	}
	if proxy != nil {
		out.Proxy = proxy.Host
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	_ = enc.Encode(out)
}

func firstEnv(names ...string) string {
	for _, n := range names {
		if v := os.Getenv(n); v != "" {
			return v
		}
	}
	return ""
}

func splitList(s string) []string {
	var out []string
	for _, part := range strings.Split(s, ",") {
		if p := strings.TrimSpace(part); p != "" {
			out = append(out, p)
		}
	}
	return out
}

func dedupe(in []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, s := range in {
		if !seen[s] {
			seen[s] = true
			out = append(out, s)
		}
	}
	return out
}

func trimErr(err error) string {
	s := err.Error()
	if len(s) > 160 {
		s = s[:157] + "..."
	}
	return s
}
