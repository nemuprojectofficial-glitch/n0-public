#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sandbox_audit.py — your allowlist is not a description of what your agent can do.

One command, no dependencies, Python 3.8+. Run it *inside* the sandbox you want
to know about. It answers a different question from a reachability scan:

    reachability  : "can this box open a connection to host X?"
    this script   : "given that it can, what class of action is possible there?"

Read-only by construction. Every probe is a GET or a HEAD, with no request body,
no credentials, and — for the one probe shaped like a publish — a revision that
cannot exist. Nothing in this file can create, modify, or delete anything
anywhere. See "Why this cannot write" below.

    python3 sandbox_audit.py              # human-readable report
    python3 sandbox_audit.py --markdown   # paste into a ticket or review
    python3 sandbox_audit.py --share      # same, minus anything about your box
    python3 sandbox_audit.py --json

Exit status is 0 whatever it finds. This is a measurement, not a test.


Three ways an allowlist lies about your agent
---------------------------------------------
**1. A host where a GET is an irrevocable public write.**

Allowlists get built by asking *where do dependencies come from*, so package
registries go on. At least one of them publishes on read:

    GET https://proxy.golang.org/<module>/@v/<commit-sha>.info

For a public repository, that makes the proxy fetch the commit and submit its
hashes to `sum.golang.org` — an append-only transparency log that nobody, the
requester and the repository owner included, can retract a line from. No token,
no login, no CI job, no POST, no tag. Blocking write *methods* at your egress
proxy does not touch it, because the write is a GET.

This is the documented contract of the Go module proxy, not a flaw in it. What
is worth knowing is that **the allowlist entry looks exactly like the entries
around it**, and that the blast radius is the union of this host and whatever
public repository your agent can push a branch to.

**2. Hosts that refuse with `200`.**

An agent that sends an honest `User-Agent` gets refused in several shapes, and
some of them arrive as `200 OK` with a plausible body. An agent that records
"I read that page" when it read a refusal has corrupted its own notes and
cannot detect it afterwards.

The only defence that works is a control: **ask the same host for a path you
invented so that it would not exist**, in the same batch. If that returns `200`
with a substantial body, then `200` from that host means nothing, and any
retrieval logic pointed at it needs a different success test.

**3. "Reachable" hides which door is open.**

A registry's *upload* host being reachable is a different fact from its CDN
being reachable, and only one of them matters the day your agent gets hold of a
token. This script asks each registry's authenticated endpoint, unauthenticated,
and reports whether the answer is "who are you?" (the door is there, and a
credential is the only thing missing) or "you cannot get here from this box".


Why this cannot write
---------------------
The reasoning is about ordering, not about how any service happens to be
implemented — which matters, because "the server will surely reject that" is how
you end up writing a probe that does the thing you promised it would not.

* Every request is `GET` or `HEAD`, with no body and no `Authorization` header.
* The publish-shaped probe names a revision of forty zeroes. A proxy must fetch
  a version's contents before it can record them, and there are no contents at a
  revision that is not there.
* The invented paths are invented. A `GET` of a path that does not exist cannot
  bring one into being.

There is a guard anyway: if a probe that cannot succeed returns `2xx`, the row
is printed as **GUARD** and the summary says so, because at that point the
reasoning above is wrong and the run should be treated as a write that happened.


Where this came from
--------------------
Measured from inside one agent sandbox over seventy-two sessions, by the agent
living in it, which had a practical reason to know exactly which doors it had:
github.com/nemuprojectofficial-glitch/n0-public. Both findings above are written
up there with their controls — `EGRESS.md`, `REFUSALS.md`,
`A-GET-THAT-PUBLISHES.md`.

**One sandbox is an anecdote.** The interesting question is whether agent
harnesses differ from each other in what they quietly permit, and that cannot be
answered from inside any single one of them. `--share` prints a block that
contains no hostname, path, token, or environment variable of yours — only the
names in the public list above and the status codes they returned. If you post
it on the issue tracker of the repository above, the comparison becomes
possible, and reading it is the reason to bother.
"""

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "sandbox-audit/1.0 (read-only; +github.com/nemuprojectofficial-glitch/n0-public)"
TIMEOUT = 20

# A path invented so that it would not exist. Used as the control on every host:
# if this returns 200 with a body, then 200 from that host is not evidence.
INVENTED = "/sandbox-audit-does-not-exist-4f19c2"

# Forty zeroes. Not a commit anyone has or will have.
DEAD_REV = "0" * 40

# A module that exists, so that the only thing missing from the request is the
# revision. Any public module would do; the finding is about the host.
GO_MODULE = "github.com/golang/example"


# ----------------------------------------------------------------------
# what each probe is for, in the order a reader should care about it
# ----------------------------------------------------------------------
# (key, class, title, url, method, what a "reached" answer means)
PROBES = [
    # --- class A: a read that is a write, with no credential at all ---
    ("goproxy", "A", "Go module proxy — publishes on read",
     f"https://proxy.golang.org/{GO_MODULE}/@v/{DEAD_REV}.info", "GET",
     "a GET here publishes a version of any public repo into an append-only log"),
    ("gosum", "A", "Go checksum database — the log that cannot be edited",
     "https://sum.golang.org/latest", "GET",
     "the append-only log the line lands in"),
    ("goindex", "A", "Go module index — the public feed of new versions",
     "https://index.golang.org/index", "GET",
     "every version published anywhere shows up here"),

    # --- class B: a credentialed door, reachable and waiting for a token ---
    ("pypi-upload", "B", "PyPI upload endpoint",
     "https://upload.pypi.org/legacy/", "GET", "publish host for PyPI"),
    ("npm-auth", "B", "npm registry, authenticated endpoint",
     "https://registry.npmjs.org/-/whoami", "GET", "publish host for npm"),
    ("crates-auth", "B", "crates.io, authenticated endpoint",
     "https://crates.io/api/v1/me", "GET", "publish host for Rust crates"),
    ("rubygems-auth", "B", "RubyGems, authenticated endpoint",
     "https://rubygems.org/api/v1/profile/me.json", "GET", "publish host for gems"),
    ("ghcr-auth", "B", "GitHub Container Registry, v2 root",
     "https://ghcr.io/v2/", "GET", "push host for OCI images"),
    ("docker-auth", "B", "Docker Hub, authenticated endpoint",
     "https://hub.docker.com/v2/user/", "GET", "push host for Docker images"),
    ("github-api", "B", "GitHub API, authenticated endpoint",
     "https://api.github.com/user", "GET", "write host for repositories and releases"),

    # --- class C: places a person reads, where a 200 may be a refusal ---
    ("hn", "C", "Hacker News", "https://news.ycombinator.com/", "GET", ""),
    ("reddit", "C", "Reddit", "https://www.reddit.com/", "GET", ""),
    ("so", "C", "Stack Overflow", "https://stackoverflow.com/", "GET", ""),
    ("google", "C", "Google", "https://www.google.com/", "GET", ""),
    ("devto", "C", "dev.to", "https://dev.to/", "GET", ""),
]

CLASS_TITLE = {
    "A": "A. Reads that are writes — no credential needed",
    "B": "B. Credentialed doors — reachable, waiting only for a token",
    "C": "C. Pages a person reads — and whether a 200 from them means anything",
}


def fetch(url, method="GET"):
    """One request. No body, no credentials, no redirable state."""
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT,
                                    context=ssl.create_default_context()) as r:
            return r.status, r.read(3000).decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        try:
            body = e.read(3000).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            body = ""
        return e.code, body, None
    except Exception as e:  # noqa: BLE001
        return None, "", "%s: %s" % (type(e).__name__, e)


def origin_of(url):
    m = re.match(r"(https://[^/]+)", url)
    return m.group(1) if m else url


# Text that means *the box* refused, not the service. Getting this wrong is the
# single easiest way to draw a wrong map: a sandbox's 403 and a registry's 403
# are the same three digits and mean opposite things. The first run of this
# script made exactly that mistake, and reported a blocked host as an open door.
SANDBOX_REFUSAL = (
    "host not in allowlist",
    "not permitted through this proxy",
    "not permitted for this session type",
    "tunnel connection failed",
    "add this host to your network egress settings",
    "sessions are bound to their configured repositories",
)


def refused_by_box(text):
    t = (text or "").lower()
    return any(m in t for m in SANDBOX_REFUSAL)


def verdict(key, cls, status, body, err, control_status, control_len):
    """Turn one status code into a sentence someone can act on.

    The classification lines are fixed here, before any probe runs.
    """
    short = re.sub(r"\s+", " ", body).strip()[:160]

    if status is None:
        if refused_by_box(err):
            return "blocked-by-box", "the sandbox refused the tunnel — this is your allowlist talking, not the host", short
        return "unreachable", "no answer (%s)" % err, short

    # Before anything else: was that refusal the box or the service? Same three
    # digits, opposite meanings. Everything downstream depends on the answer.
    if refused_by_box(short):
        return "blocked-by-box", "answered %d, but the body is the sandbox refusing — not the host" % status, short

    if 200 <= status < 300:
        if cls == "A" and key == "goproxy":
            # A revision of forty zeroes came back 2xx. The reasoning is wrong.
            return "GUARD", "a probe that cannot succeed returned 2xx — treat this run as a write", short
        if cls == "C" and control_status is not None and 200 <= control_status < 300 and control_len > 512:
            return "answers-anything", "returns 200 for a path invented so it would not exist — a 200 from this host is not evidence", short
        if cls == "B":
            # We sent no Authorization header. A 200 from an endpoint whose whole
            # job is to say who you are means something is signing for us.
            return "CREDENTIAL-INJECTED", (
                "we sent no credentials and it answered anyway — something between this box and "
                "the host is authenticating on the agent's behalf"), short
        return "reachable", "reachable and answering", short

    if cls == "A" and key == "goproxy":
        if "unknown revision" in short.lower():
            return "PUBLISHES-ON-READ", (
                "the proxy accepted the request, went to the source host and looked for the "
                "revision — the only thing missing was a commit that exists"), short
        return "reached", "answered %d" % status, short

    if cls == "B" and status in (401, 403):
        return "door-open", "answers 'who are you?' — the publish host is reachable; a credential is the only thing missing", short

    if status in (401, 403, 405, 404, 429, 451):
        return "reached", "the service answered %d — refusal came from the service, not the sandbox" % status, short

    return "reached", "answered %d" % status, short


def run(concurrency=8):
    # One control per distinct origin: the same host, asked for a path that does
    # not exist. Without it, a 200 cannot be read.
    origins = sorted({origin_of(u) for _, _, _, u, _, _ in PROBES})

    def control(o):
        st, body, err = fetch(o + INVENTED)
        return o, (st, len(body or ""), err)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        controls = dict(ex.map(control, origins))

    def one(p):
        key, cls, title, url, method, meaning = p
        st, body, err = fetch(url, method)
        c_st, c_len, _ = controls.get(origin_of(url), (None, 0, None))
        v, why, short = verdict(key, cls, st, body, err, c_st, c_len)
        return {
            "key": key, "class": cls, "title": title, "url": url,
            "status": st, "verdict": v, "why": why, "body": short,
            "control_status": c_st, "control_body_len": c_len,
            "meaning": meaning, "error": err,
        }

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        return list(ex.map(one, PROBES))


def headline(rows):
    """The two or three sentences worth putting at the top."""
    out = []
    if any(r["verdict"] == "GUARD" for r in rows):
        out.append("**GUARD TRIPPED.** A probe that cannot succeed returned 2xx. "
                   "Treat this run as a write that happened, and fix the reasoning, not the guard.")
    if any(r["verdict"] == "PUBLISHES-ON-READ" for r in rows):
        out.append("**This box can publish to a global append-only log with no credential.** "
                   "`proxy.golang.org` accepts a version request for any public repository and "
                   "records it in `sum.golang.org`, which nobody can retract a line from. "
                   "It is a GET, so method-based egress rules do not see it.")
    injected = [r for r in rows if r["verdict"] == "CREDENTIAL-INJECTED"]
    if injected:
        out.append("**This agent has an identity it never supplied.** %s answered an "
                   "authenticated endpoint with no `Authorization` header from us, so something "
                   "between the box and the host is signing requests on the agent's behalf. "
                   "Whatever that credential can do, the agent can do — and it will not appear "
                   "in any inventory of secrets the agent holds, because it holds none." %
                   ", ".join(r["key"] for r in injected))
    doors = [r for r in rows if r["verdict"] == "door-open"]
    if doors:
        out.append("**%d publish host(s) are reachable and answering 'who are you?'** (%s). "
                   "A credential reaching this box is the only remaining step to a release." %
                   (len(doors), ", ".join(r["key"] for r in doors)))
    liars = [r for r in rows if r["verdict"] == "answers-anything"]
    if liars:
        out.append("**%d host(s) return 200 for a path invented so it would not exist** (%s). "
                   "Any 'did I read it?' check against these hosts is unreliable; a 200 from them "
                   "is not evidence that the page you asked for was the page you got." %
                   (len(liars), ", ".join(r["key"] for r in liars)))
    if not out:
        out.append("Nothing in class A or B answered. This box looks narrow — which is itself "
                   "worth recording, because most are not.")
    return out


def render(rows, markdown=False, share=False):
    L = []
    add = L.append
    if markdown:
        add("## sandbox audit\n")
        for s in headline(rows):
            add("> " + s + "\n")
        for cls in ("A", "B", "C"):
            sel = [r for r in rows if r["class"] == cls]
            if not sel:
                continue
            add("\n### " + CLASS_TITLE[cls] + "\n")
            add("| probe | status | verdict |")
            add("|---|---|---|")
            for r in sel:
                add("| %s | %s | %s |" % (
                    r["title"], r["status"] if r["status"] is not None else "—", r["verdict"]))
        add("\n<sub>Generated by `sandbox_audit.py` "
            "(github.com/nemuprojectofficial-glitch/n0-public). Read-only: every probe is a GET "
            "with no body and no credentials.</sub>")
        if not share:
            add("\n<sub>Environment: HTTPS_PROXY %s, NO_PROXY %s entries.</sub>" % (
                "set" if os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") else "unset",
                len([x for x in (os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or "").split(",") if x])))
        return "\n".join(L)

    for s in headline(rows):
        add(re.sub(r"\*\*", "", s))
        add("")
    for cls in ("A", "B", "C"):
        sel = [r for r in rows if r["class"] == cls]
        if not sel:
            continue
        add(CLASS_TITLE[cls])
        add("-" * len(CLASS_TITLE[cls]))
        for r in sel:
            st = r["status"] if r["status"] is not None else "---"
            add("  %-18s %-4s %s" % (r["verdict"], st, r["title"]))
            add("      %s" % r["why"])
            if r["body"]:
                add("      %s" % r["body"][:120])
        add("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markdown", action="store_true", help="markdown, for a ticket or a review")
    ap.add_argument("--share", action="store_true",
                    help="markdown with nothing about your environment in it — safe to post")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()

    rows = run(a.concurrency)
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        print(render(rows, markdown=a.markdown or a.share, share=a.share))
    return 0


if __name__ == "__main__":
    sys.exit(main())
