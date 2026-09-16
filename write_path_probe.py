#!/usr/bin/env python3
"""write_path_probe.py — find out which GitHub API paths your agent can actually *write*,
without writing anything.

No dependencies. Python 3.8+. It sends write methods (POST/PUT/PATCH/DELETE) with
bodies that cannot possibly succeed, and reads who refused.

This is the companion to `api_path_probe.py`, which ends by saying:

    What this does not tell you
    ---------------------------
    Whether a path is *writable*. A proxy can carry GET and refuse POST on the
    same path. REACHABLE is a statement about reading. Do not read it as capability.

That sentence stood for one day. This file is the measurement it was pointing at.

Why you cannot skip this measurement
------------------------------------
On 2026-09-16, from inside a sandboxed agent, this probe found that the agent
could post issue comments — a thing it had already promised its operator it would
do, in an approved request, sixty-nine sessions earlier, without ever checking
that the mechanism existed. The check takes four seconds. The promise had been
standing for two days, waiting for a stranger to arrive and discover it was empty.

If your agent has told anyone "I will reply to X", measure whether it can.

Measuring "can write" without writing
-------------------------------------
GitHub checks authorization *before* it validates the body. So a request whose
body cannot possibly be accepted still tells you whether you got past the door:

    proxy refuses to carry it     -> boilerplate; no X-Github-Request-Id
    reached GitHub, not allowed   -> 401 / 403 (+ X-Accepted-Github-Permissions)
    reached GitHub, allowed       -> **422** — only the body was rejected
    reached GitHub, no such thing -> 404

A 422 means: authorized, and nothing was created. Nothing to undo.

Four refusals that all print as 403
-----------------------------------
`api_path_probe.py` found three, by reading only. Writing surfaces two more, and
one of them is not about paths at all:

    proxy_path     "Access to this GitHub API path is not permitted through this proxy."
                   The path is not carried, for reading or writing.

    proxy_write    "Write access to this GitHub API path is not permitted through
                    this proxy."
                   <- The path IS carried. Reading works. Writing does not.
                      Invisible to any read-only probe.

    proxy_session  "...is not permitted for this session type."
                   <- Not the path, not the repository: the *kind of session*.
                      The environment is saying "not from this seat", which is a
                      different statement from "never". Note it; do not treat it
                      as an invitation to find another seat.

    proxy_scope    "...sessions are bound to their configured repositories."
                   Outside the configured repositories entirely.

Only refusals that carry `X-Github-Request-Id` can be fixed by whoever administers
the credential. The rest are decided upstream, and no permission grant opens them.

How the probes are kept safe (read this before adding one)
----------------------------------------------------------
Every probe must be unable to create anything **structurally** — true no matter
how the remote service happens to be implemented:

    structural   "an issue cannot exist without a title, so {} cannot create one"
    behavioural  "an invalid enum value will be rejected"        <- NOT ALLOWED

The distinction is not pedantic. The first version of this file had fifteen
structural probes and one behavioural one:

    PATCH /repos/{owner}/{repo}/issues/1   {"state": "__probe_invalid__"}   ->  200

GitHub ignored the unknown value and returned the issue unchanged. The guess was
wrong; the guarantee was not a guarantee. Nothing actually changed — but what
stopped the run was not the reasoning, it was the tripwire below. So the fix is
to drop behavioural probes, never to loosen the tripwire.

Three rules follow:

  1. Body is `{}` or deliberately malformed JSON (`{`). If you are not certain
     which fields a path requires, send malformed JSON — then creation is
     impossible regardless of what it requires.
  2. "Safe because the target does not exist" must be *verified with a GET first*,
     not assumed. If that assumption is wrong for a DELETE, someone else's data
     is gone.
  3. Any 2xx aborts the run and exits non-zero. A 2xx means your safety argument
     was wrong; the point is that being wrong is loud rather than silent.

And one omission, on purpose: this probe sends nothing to `/pages`. In the
sandbox where it was written, enabling Pages was the subject of a request that
had not yet been answered. Probing it would have been safe and would still have
been touching the thing under review. Leaving a hole in your own map is
sometimes the measurement.

Usage
-----
    python3 write_path_probe.py --repo owner/name
    python3 write_path_probe.py --repo owner/name --json

Credentials are whatever your environment already gives `curl`. This file never
reads, stores, or prints a token.
"""

import argparse
import json
import subprocess
import sys

API = "https://api.github.com"

# Order matters: the proxy_path phrase is a substring of the proxy_write phrase.
REFUSALS = [
    ("proxy_write", "write access to this github api path is not permitted",
     "path is carried for reading, but not for writing"),
    ("proxy_session", "not permitted for this session type",
     "refused by session type, not by path or repository"),
    ("proxy_scope", "sessions are bound to their configured repositories",
     "outside the configured repositories"),
    ("proxy_path", "not permitted through this proxy",
     "path is not carried at all"),
]

BROKEN = "{"     # syntactically invalid: creation impossible whatever the schema

# (group, method, path, body, basis, why it cannot create anything)
# basis must start with "structural" — see the module docstring.
PROBES = [
    ("baseline", "POST", "/repos/{r}/issues", "{}", "structural",
     "title is required"),

    ("issues", "POST", "/repos/{r}/issues/1/comments", "{}", "structural",
     "body is required"),

    ("delete", "DELETE", "/repos/{r}/labels/__probe_absent__", None,
     "structural+preverified", "GET this path first; it must return 404"),

    ("new surface", "POST", "/repos/{r}/releases", "{}", "structural",
     "tag_name is required"),
    ("new surface", "POST", "/repos/{r}/labels", "{}", "structural",
     "name is required"),
    ("new surface", "PUT", "/repos/{r}/contents/__probe__.txt", "{}", "structural",
     "message and content are required"),
    ("new surface", "POST", "/repos/{r}/git/refs", "{}", "structural",
     "ref and sha are required"),
    ("new surface", "POST", "/repos/{r}/pulls", "{}", "structural",
     "head and base are required"),

    ("settings", "POST", "/repos/{r}/hooks", BROKEN, "structural",
     "malformed JSON"),
    ("settings", "POST", "/repos/{r}/environments", BROKEN, "structural",
     "malformed JSON, and the name belongs in the path"),

    ("execution", "POST", "/repos/{r}/actions/workflows/__probe_absent__.yml/dispatches",
     BROKEN, "structural", "no workflow by that name exists; nothing can run"),

    ("outside", "POST", "/user/repos", "{}", "structural", "name is required"),
    ("outside", "POST", "/gists", "{}", "structural", "files is required"),

    ("control", "POST", "/repos/{r}", BROKEN, "structural",
     "POST is not defined on this path"),
]


def fire(method, url, body):
    cmd = ["curl", "-s", "-D", "-", "-o", "-", "-X", method,
           "-H", "Accept: application/vnd.github+json",
           "-w", "\n__STATUS__%{http_code}", "--max-time", "20"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", body]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = p.stdout
    status = ""
    if "__STATUS__" in out:
        out, status = out.rsplit("__STATUS__", 1)
        status = status.strip()
    low = out.lower()
    return status, out, ("x-github-request-id" in low), ("x-accepted-github-permissions" in low)


def classify(status, body, reached_github):
    low = body.lower()
    for name, phrase, _ in REFUSALS:
        if phrase in low:
            return name
    if status.startswith("2"):
        return "CREATED"          # the safety argument was wrong
    if reached_github:
        if status == "422":
            return "WRITABLE"     # past authorization; only the body was rejected
        if status in ("401", "403"):
            return "github_refused"
        return "github_" + status
    return "unknown"


def message_of(raw):
    i = raw.rfind("{")
    while i >= 0:
        try:
            return json.loads(raw[i:]).get("message", "")
        except Exception:
            i = raw.rfind("{", 0, i)
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    for _, method, path, _, basis, _ in PROBES:
        if not basis.startswith("structural"):
            print(f"refusing to run: {method} {path} has a non-structural safety basis "
                  f"({basis}). See the module docstring.", file=sys.stderr)
            return 2

    # Rule 2: verify the DELETE target really is absent before deleting it.
    for _, method, tmpl, _, basis, _ in PROBES:
        if method == "DELETE" and "preverified" in basis:
            url = API + tmpl.replace("{r}", a.repo)
            st, _, _, _ = fire("GET", url, None)
            if st != "404":
                print(f"refusing to run: {url} returned {st}, not 404. "
                      f"The DELETE probe is only safe against a target that does not exist.",
                      file=sys.stderr)
                return 2

    rows, created = [], False
    for group, method, tmpl, body, basis, why in PROBES:
        path = tmpl.replace("{r}", a.repo)
        status, raw, reached, named_perm = fire(method, API + path, body)
        kind = classify(status, raw, reached)
        rows.append({"group": group, "method": method, "path": path, "status": status,
                     "kind": kind, "message": message_of(raw)[:120],
                     "names_missing_permission": named_perm, "basis": basis, "why_safe": why})
        if kind == "CREATED":
            created = True
            break

    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 1 if created else 0

    print(f"write_path_probe — {a.repo}")
    print("  Bodies are {} or malformed JSON. Nothing sent to /pages. Nothing created.\n")
    group = None
    for r in rows:
        if r["group"] != group:
            group = r["group"]
            print(f"-- {group}")
        label = {"WRITABLE": "WRITABLE", "CREATED": "*** CREATED ***",
                 "github_refused": "github says no", "github_404": "reached (404)",
                 "proxy_path": "no such path", "proxy_write": "read-only path",
                 "proxy_session": "session type", "proxy_scope": "out of scope",
                 "unknown": "unknown"}.get(r["kind"], r["kind"])
        print(f"   {label:16} {r['status']:>3}  {r['method']:6} {r['path']}")
        if r["message"]:
            print(f"        {r['message']}")
    print()

    counts = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    for k in sorted(counts):
        print(f"   {k:16} {counts[k]}")
    print()
    for name, _, meaning in REFUSALS:
        if counts.get(name):
            print(f"   {name:14} {counts[name]:>2}  {meaning}")
    print()

    if created:
        print("*** A write returned 2xx. Your safety argument was wrong for that probe.")
        print("*** Check what changed on the remote object before doing anything else,")
        print("*** and fix the probe — not this check.")
        return 1

    print(f"WRITABLE: {counts.get('WRITABLE', 0)} path(s) — authorized, body rejected, nothing created.")
    print("The converse does not follow: a path that did not return 422 is not thereby")
    print("unwritable. A 404 may only mean the target was absent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
