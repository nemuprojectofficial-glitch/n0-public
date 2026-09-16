#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""goproxy_write_probe — show that a Go module proxy answers publish requests,
without publishing anything.

Companion to A-GET-THAT-PUBLISHES.md. No dependencies. Python 3.8+.

    python3 goproxy_write_probe.py
    python3 goproxy_write_probe.py --json
    python3 goproxy_write_probe.py --module github.com/you/your-public-repo

Why this is safe to run
-----------------------
A module proxy has to fetch a version's contents before it can record them, and
there are no contents at a revision that does not exist. Every probe below uses
a revision that cannot exist:

    000000000000                                (12-hex pseudo-version SHA)
    0000000000000000000000000000000000000000    (40-hex commit SHA)
    a module path under a repository name that does not exist

So no version can be created by anything in this file. That is an argument about
ordering — fetch precedes record — not an argument about how any particular
proxy is implemented. The distinction matters: reasoning from expected
*behaviour* is how you write a probe that does the thing you promised it
wouldn't.

There is a guard anyway. If any probe that is supposed to be impossible returns
2xx, this exits 1 and says so, because at that point the reasoning above is
wrong and the run needs to be treated as a write that happened.

What it can and cannot tell you
-------------------------------
    can    : whether the host is reachable, whether the proxy accepts the
             pseudo-version and bare-SHA request forms, and whether it actually
             goes to the source host to resolve a revision
    cannot : whether *your* commit would publish. Finding that out is the
             publication. sum.golang.org is append-only and nobody can retract
             a line from it, so there is no order of operations in which you
             measure that step before taking it.
"""

import argparse
import json
import re
import ssl
import sys
import urllib.error
import urllib.request

PROXY = "https://proxy.golang.org"
DEFAULT_MODULE = "github.com/nemuprojectofficial-glitch/n0-public"
DEAD12 = "0" * 12
DEAD40 = "0" * 40

# Words that show the proxy went to the source host instead of rejecting the
# request on its shape alone. Fixed here before the probes run.
WENT_TO_SOURCE = ("unknown revision", "unknown import path", "no matching versions",
                  "git ls-remote")


def probes(module):
    missing = module.rsplit("/", 1)[0] + "/__probe_module_does_not_exist__"
    return [
        ("list", "versions already published (read-only)",
         f"{PROXY}/{module}/@v/list",
         "read-only listing", False),
        ("pseudo", "pseudo-version built on a SHA that does not exist",
         f"{PROXY}/{module}/@v/v0.0.0-00010101000000-{DEAD12}.info",
         f"revision {DEAD12} does not exist, so there are no contents to record", True),
        ("bare-sha", "bare commit SHA that does not exist",
         f"{PROXY}/{module}/@v/{DEAD40}.info",
         f"revision {DEAD40[:12]}… does not exist, so there are no contents to record", True),
        ("control", "module path whose repository does not exist",
         f"{missing}/@v/list".replace(missing, f"{PROXY}/{missing}"),
         "no repository, so there is nothing to fetch", True),
    ]


def fire(url, timeout=30):
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "goproxy-write-probe/1.0 (read-only)")
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context()) as r:
            return r.status, r.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(4000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", default=DEFAULT_MODULE,
                    help="module path to probe (must be a PUBLIC repository)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows, tripped = [], []
    for key, what, url, why_safe, must_fail in probes(a.module):
        code, body = fire(url)
        short = re.sub(r"\s+", " ", body).strip()[:240]
        hits = [w for w in WENT_TO_SOURCE if w in short.lower()]
        rows.append({"probe": key, "what": what, "url": url,
                     "why_nothing_is_created": why_safe,
                     "status": code, "body": short, "reached_source": hits})
        if must_fail and code is not None and 200 <= code < 300:
            tripped.append(key)

    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"module: {a.module}\n")
        for r in rows:
            print(f"── {r['probe']}: {r['what']}")
            print(f"   {r['url']}")
            print(f"   HTTP {r['status']}  {r['body'][:180]}")
            if r["reached_source"]:
                print(f"   → reached the source host: {r['reached_source']}")
            print()

    if tripped:
        print(f"GUARD TRIPPED: probes that cannot succeed returned 2xx: {tripped}",
              file=sys.stderr)
        print("Treat this run as a write that happened, and fix the reasoning, "
              "not the guard.", file=sys.stderr)
        return 1

    print("-" * 64)
    print("No version was published by this run: every probe above names a "
          "revision that does not exist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
