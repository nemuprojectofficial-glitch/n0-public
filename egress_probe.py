#!/usr/bin/env python3
"""egress_probe.py — map what an agent sandbox can actually reach, from inside it.

No dependencies. Python 3.8+. Read-only: it opens connections and reads status
lines. It never sends a request body, never authenticates, never writes anything
anywhere.

Why this exists
---------------
An agent running in a sandbox is usually told "network access is governed by an
allowlist" and is not shown the list. The list decides which distribution
channels exist for that agent, so not knowing it is not a small gap. This script
recovers the answer empirically, one host at a time.

How the classification works
----------------------------
Traffic leaves through an HTTP CONNECT proxy named by $HTTPS_PROXY, except for
hosts matching $NO_PROXY, which go direct. So there are two probes:

  proxied host   send `CONNECT host:443` to the proxy and read its status line
                 200  -> the allowlist permits this host (tunnel opened)
                 403  -> the allowlist does not permit this host
  direct host    open a TCP connection to host:443

Then, for hosts that got through, optionally complete a TLS handshake and send
`HEAD /` to see whether the origin answers. An origin's own 403 (npm, PyPI's
upload endpoint) still means REACHABLE — the refusal came from the service, not
from the sandbox.

  REACHABLE  the sandbox let the connection out and something answered
  BLOCKED    the proxy refused the tunnel
  NO_HOST    permitted, but DNS or TCP failed (host does not exist / is down)

Usage
-----
  python3 egress_probe.py                    # probe the built-in host list
  python3 egress_probe.py --hosts a.com b.io # probe specific hosts
  python3 egress_probe.py --file hosts.txt   # one host per line
  python3 egress_probe.py --json             # machine-readable output

Exit status is 0 whatever the findings; this is a measurement, not a test.
"""

import argparse
import json
import os
import socket
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

TIMEOUT = 12.0

# A starting list, grouped by what the host would let an agent *do*.
# Publishing surfaces come first: those are the ones that decide whether an
# agent can reach anyone at all.
DEFAULT_HOSTS = [
    # package registries — an agent that can write here can distribute software
    "pypi.org", "upload.pypi.org", "test.pypi.org", "files.pythonhosted.org",
    "registry.npmjs.org", "www.npmjs.com",
    "crates.io", "static.crates.io",
    "rubygems.org", "packagist.org", "hex.pm", "api.nuget.org",
    "repo1.maven.org", "anaconda.org", "conda.anaconda.org",
    "proxy.golang.org", "pkg.go.dev", "jsr.io",
    # container registries
    "ghcr.io", "index.docker.io", "registry-1.docker.io", "hub.docker.com",
    # code hosts
    "github.com", "api.github.com", "raw.githubusercontent.com",
    "codeload.github.com", "objects.githubusercontent.com", "gist.github.com",
    "gitlab.com", "bitbucket.org", "codeberg.org", "gitea.com", "git.sr.ht",
    "sourceforge.net", "launchpad.net",
    # OS package repositories
    "archive.ubuntu.com", "deb.debian.org",
    # CDNs
    "cdn.jsdelivr.net", "unpkg.com", "esm.sh",
    # places where people read and reply — the push channels
    "news.ycombinator.com", "lobste.rs", "www.reddit.com", "dev.to",
    "zenn.dev", "qiita.com", "note.com", "stackoverflow.com",
    "api.stackexchange.com", "x.com", "bsky.app", "public.api.bsky.app",
    "mastodon.social", "discord.com", "api.telegram.org",
    # search engines
    "www.google.com", "duckduckgo.com", "www.bing.com",
    # money
    "api.stripe.com", "ko-fi.com", "buymeacoffee.com", "gumroad.com", "polar.sh",
    # controls: neither should ever be REACHABLE
    "example.com", "this-host-should-not-exist-egress-probe.invalid",
]


def no_proxy_patterns():
    raw = os.environ.get("no_proxy") or os.environ.get("NO_PROXY") or ""
    return [p.strip().lower().lstrip("*") for p in raw.split(",") if p.strip()]


def goes_direct(host, patterns):
    """Mirror curl's NO_PROXY matching: exact host, or domain suffix."""
    h = host.lower()
    for p in patterns:
        if not p:
            continue
        if p.startswith("."):
            if h == p[1:] or h.endswith(p):
                return True
        elif h == p or h.endswith("." + p):
            return True
    return False


def proxy_endpoint():
    raw = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if not raw:
        return None
    u = urlparse(raw if "://" in raw else "http://" + raw)
    return (u.hostname, u.port or 8080)


def open_tunnel(proxy, host, port=443):
    """Return (socket, proxy_status). socket is None unless the tunnel opened."""
    sock = socket.create_connection(proxy, timeout=TIMEOUT)
    try:
        req = "CONNECT {h}:{p} HTTP/1.1\r\nHost: {h}:{p}\r\n\r\n".format(h=host, p=port)
        sock.sendall(req.encode())
        line = b""
        while not line.endswith(b"\r\n"):
            chunk = sock.recv(1)
            if not chunk:
                break
            line += chunk
        parts = line.decode("latin-1").split()
        status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        if status != 200:
            sock.close()
            return None, status
        # drain the rest of the proxy's response headers
        rest = b""
        while b"\r\n\r\n" not in rest and b"\n\n" not in rest:
            chunk = sock.recv(1)
            if not chunk:
                break
            rest += chunk
            if rest.endswith(b"\r\n"):
                break
        return sock, status
    except Exception:
        sock.close()
        raise


def origin_status(sock, host):
    """Complete TLS and send HEAD /. Returns the origin's status code, or None."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # we are measuring reachability, not trust
    tls = ctx.wrap_socket(sock, server_hostname=host)
    tls.settimeout(TIMEOUT)
    req = ("HEAD / HTTP/1.1\r\nHost: {h}\r\n"
           "User-Agent: egress-probe (read-only reachability check)\r\n"
           "Connection: close\r\n\r\n").format(h=host)
    tls.sendall(req.encode())
    line = tls.recv(256).decode("latin-1", "replace").split("\r\n")[0]
    tls.close()
    parts = line.split()
    return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None


def probe(host, proxy, patterns):
    # A host is only *proxied* if a proxy exists at all. Labelling the route
    # from $NO_PROXY alone was wrong on any machine without $HTTPS_PROXY set:
    # every connection was made directly and then, on failure, blamed on a
    # proxy that was never there. Found by running this same probe from a CI
    # runner, where there is no proxy and every failure came back BLOCKED.
    # That is the exact confusion this file's own docstring warns about.
    proxied = bool(proxy) and not goes_direct(host, patterns)
    direct = not proxied
    row = {"host": host, "route": "proxy" if proxied else "direct",
           "verdict": None, "proxy_status": None, "origin_status": None,
           "detail": ""}
    try:
        if direct:
            sock = socket.create_connection((host, 443), timeout=TIMEOUT)
        else:
            sock, status = open_tunnel(proxy, host)
            row["proxy_status"] = status
            if sock is None:
                row["verdict"] = "BLOCKED"
                row["detail"] = "proxy refused CONNECT with %d" % status
                return row
        try:
            row["origin_status"] = origin_status(sock, host)
        except Exception as exc:
            row["detail"] = "connected, TLS/HTTP failed: %s" % type(exc).__name__
        row["verdict"] = "REACHABLE"
        return row
    except socket.gaierror:
        row["verdict"] = "NO_HOST"
        row["detail"] = "DNS did not resolve"
    except Exception as exc:
        row["verdict"] = "NO_HOST" if direct else "BLOCKED"
        row["detail"] = "%s: %s" % (type(exc).__name__, exc)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hosts", nargs="+", help="hosts to probe")
    ap.add_argument("--file", help="file with one host per line")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    hosts = list(args.hosts or [])
    if args.file:
        with open(args.file) as fh:
            hosts += [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    hosts = hosts or DEFAULT_HOSTS

    proxy = proxy_endpoint()
    patterns = no_proxy_patterns()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda h: probe(h, proxy, patterns), hosts))

    if args.json:
        print(json.dumps({"proxy": ":".join(map(str, proxy)) if proxy else None,
                          "results": rows}, indent=2, ensure_ascii=False))
        return 0

    print("proxy: %s" % (":".join(map(str, proxy)) if proxy else "(none set)"))
    print("%d hosts probed\n" % len(rows))
    order = {"REACHABLE": 0, "NO_HOST": 1, "BLOCKED": 2}
    for r in sorted(rows, key=lambda r: (order.get(r["verdict"], 3), r["host"])):
        origin = r["origin_status"]
        note = "origin %s" % origin if origin else r["detail"]
        print("%-10s %-6s %-38s %s" % (r["verdict"], r["route"], r["host"], note))

    reach = sum(1 for r in rows if r["verdict"] == "REACHABLE")
    print("\nREACHABLE %d / BLOCKED %d / NO_HOST %d"
          % (reach,
             sum(1 for r in rows if r["verdict"] == "BLOCKED"),
             sum(1 for r in rows if r["verdict"] == "NO_HOST")))
    print("\nAn origin's own 4xx still counts as REACHABLE: the refusal came "
          "from the service, not from the sandbox.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
