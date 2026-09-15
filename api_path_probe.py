#!/usr/bin/env python3
"""api_path_probe.py — find out which GitHub API paths your agent can actually use.

No dependencies. Python 3.8+. Read-only: it sends `GET` and nothing else. It
never sends a request body, never writes, never retries around a refusal.

Why this exists
---------------
An agent given GitHub access is usually told something like "the API is scoped
to the configured repositories." That sentence describes a boundary drawn around
*repositories*. On 2026-09-15, from inside such a sandbox, the boundary turned
out to be drawn around (repository x path):

    GET /repos/{owner}/{repo}          -> 200, permissions.admin = true
    GET /repos/{owner}/{repo}/pages    -> 403, "not permitted through this proxy"

Same repository. Same credential. One path allowed, the next one not. Sixty-eight
sessions of notes in this repository describe the boundary as repository-shaped,
because a 403 had never been asked *which machine sent it*.

Three refusals that all print as 403
------------------------------------
    proxy_path   the agent's API proxy does not carry this path at all
                 body: "Access to this GitHub API path is not permitted
                        through this proxy."
    proxy_scope  the path is not repository-scoped, so the proxy rejects it
                 body: "...sessions are bound to their configured repositories."
    github       the request reached GitHub and GitHub refused it
                 header: X-Github-Request-Id
                 header: X-Accepted-Github-Permissions  <- on a 403, names what is missing
                                              (it is also sent on success, where
                                               it is not a diagnosis)

Why the difference is not academic: only the third kind can be fixed by whoever
administers the credential. The first two are decided upstream of GitHub, and no
permission grant will open them. An agent that files a request with its operator
saying "please open the traffic API" is asking the right person only if the 403
was GitHub's. Reading the header turns a nine-day-old open request into one line:
grant `Administration: Read-only`.

What this does not tell you
---------------------------
Whether a path is *writable*. A proxy can carry GET and refuse POST on the same
path. REACHABLE is a statement about reading. Do not read it as capability.

  python3 api_path_probe.py --repo owner/name
  python3 api_path_probe.py --repo owner/name --json
  python3 api_path_probe.py --repo owner/name --paths /repos/{r}/pages /user

Exit status is 0 whatever the findings; this is a measurement, not a test.
"""

import argparse
import json
import subprocess
import sys

API = "https://api.github.com"
PROXY_PATH_MARK = "not permitted through this proxy"
PROXY_SCOPE_MARK = "bound to their configured repositories"

# Grouped by what the path would let an agent *do*, not by how famous it is.
DEFAULT_PATHS = [
    # baseline — if these fail, nothing else can be read
    "/repos/{r}", "/rate_limit", "/user",
    # inbound: can the world reach the agent, and can the agent see that it did
    "/repos/{r}/issues", "/repos/{r}/stargazers", "/repos/{r}/subscribers",
    "/repos/{r}/forks", "/repos/{r}/events",
    # arrival: the only endpoints that count visitors
    "/repos/{r}/traffic/views", "/repos/{r}/traffic/clones",
    "/repos/{r}/traffic/popular/paths", "/repos/{r}/traffic/popular/referrers",
    # new surfaces: each one is a distribution channel that did not exist before
    "/repos/{r}/pages", "/repos/{r}/releases", "/repos/{r}/topics", "/gists",
    # repository configuration
    "/repos/{r}/hooks", "/repos/{r}/environments", "/repos/{r}/deployments",
    "/repos/{r}/collaborators", "/repos/{r}/branches", "/repos/{r}/labels",
    # compute the agent can start
    "/repos/{r}/actions/workflows", "/repos/{r}/actions/runs",
    # history and supply chain
    "/repos/{r}/commits", "/repos/{r}/tags", "/repos/{r}/pulls",
    "/repos/{r}/dependency-graph/sbom", "/repos/{r}/community/profile",
    # outside the scope — controls. A vantage point that answered "reachable"
    # to everything would be measuring nothing.
    "/search/repositories?q=stars:>1", "/users/github",
]


def get(url):
    p = subprocess.run(
        ["curl", "-s", "-D", "-", "-o", "-", "-X", "GET",
         "-H", "Accept: application/vnd.github+json",
         "-w", "\n__STATUS__%{http_code}", "--max-time", "20", url],
        capture_output=True, text=True,
    )
    out, status = p.stdout, ""
    if "__STATUS__" in out:
        out, status = out.rsplit("__STATUS__", 1)
        status = status.strip()
    return status, out


def header(raw, name):
    for line in raw.splitlines():
        if line.lower().startswith(name + ":"):
            return line.split(":", 1)[1].strip()
    return ""


def classify(status, raw):
    if PROXY_PATH_MARK in raw:
        return "proxy_path"
    if PROXY_SCOPE_MARK in raw:
        return "proxy_scope"
    if header(raw, "x-github-request-id"):
        if status.startswith("2"):
            return "github_ok"
        return "github_" + status
    return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--paths", nargs="*", help="override the built-in path list")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = []
    for tmpl in (a.paths or DEFAULT_PATHS):
        path = tmpl.replace("{r}", a.repo)
        status, raw = get(API + path)
        kind = classify(status, raw)
        body = raw.split("\r\n\r\n", 1)[-1] if "\r\n\r\n" in raw else raw
        msg = ""
        try:
            msg = json.loads(body).get("message", "")
        except Exception:
            pass
        # GitHub sends X-Accepted-Github-Permissions on success *and* on
        # refusal. It is the set of permissions the endpoint accepts, not a
        # diagnosis. Only on a 403 does it tell you what you are missing, so
        # only there is it reported that way.
        accepted = header(raw, "x-accepted-github-permissions")
        rows.append({
            "path": path,
            "status": status,
            "kind": kind,
            "message": msg[:100],
            "accepted_permissions": accepted,
            "missing_permission": accepted if kind == "github_403" else "",
        })

    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0

    label = {
        "github_ok": "REACHABLE",
        "github_403": "GITHUB   ",
        "github_404": "REACHABLE",
        "proxy_path": "PROXY    ",
        "proxy_scope": "OUT-OF-SCOPE",
        "unknown": "UNKNOWN  ",
    }
    counts = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
        extra = ""
        if r["missing_permission"]:
            extra = "   grant one of: " + r["missing_permission"]
        elif r["kind"] != "github_ok" and r["message"]:
            extra = "   << " + r["message"]
        print(f"  {label.get(r['kind'], r['kind']):12} {r['status']:>3}  {r['path']}{extra}")

    print()
    for k in sorted(counts):
        print(f"  {k:14} {counts[k]}")
    print("\n  REACHABLE means the request reached GitHub and was answered.")
    print("  It does not mean the path is writable. GET and POST can differ.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
