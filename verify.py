#!/usr/bin/env python3
"""
verify.py — an append-only ledger verifier for autonomous agents.

An agent that keeps its own records can quietly rewrite them. This checks that
it did not, using git history as the tamper-evidence, plus three consistency
checks over the ledger's contents.

No dependencies. Python 3.8+. Needs `git` on PATH.

    python3 verify.py                     # verify ./audit in this repo
    python3 verify.py --ledger audit --initial-balance 1000
    python3 verify.py --json              # machine-readable

Exit code 0 if every check passes, 1 if any check fails, 2 on usage error.

See SPEC.md for the ledger format this expects.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

# --- the four checks, by name ------------------------------------------------

CHECK_APPEND_ONLY = "append_only"
CHECK_EXTERNAL_CLAIMED = "external_has_claim"
CHECK_BALANCE = "balance_consistent"
CHECK_PREDICTIONS = "predictions_resolved"


class Failure:
    def __init__(self, check, where, detail):
        self.check = check
        self.where = where
        self.detail = detail

    def as_dict(self):
        return {"check": self.check, "where": self.where, "detail": self.detail}

    def __str__(self):
        return "  {}\n      {}".format(self.where, self.detail)


# --- git plumbing -------------------------------------------------------------


def git(repo, *args):
    proc = subprocess.run(
        ["git", "-C", repo] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "git {} failed: {}".format(" ".join(args), proc.stderr.decode("utf-8", "replace").strip())
        )
    return proc.stdout.decode("utf-8", "replace")


def has_commits(repo):
    """False for a repository whose HEAD is unborn (nothing committed yet)."""
    proc = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--verify", "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def commit_graph(repo):
    """Every commit reachable from HEAD, oldest first, as (sha, [parents]).

    Deliberately not `git log -- <path>`: path-limited log applies history
    simplification and drops merge commits whose result matches a parent, which
    is exactly where a concurrent append can lose a line. The check has to walk
    real parent edges or it cannot see what happened at a merge.
    """
    out = git(repo, "log", "--reverse", "--format=%H %P", "HEAD")
    graph = []
    for line in out.splitlines():
        parts = line.split()
        if parts:
            graph.append((parts[0], parts[1:]))
    return graph


def blob_shas(repo, revs, path):
    """{rev: blob sha or None} for `<rev>:<path>`, in a single git call.

    One process for the whole history rather than one per commit, so the check
    stays usable as the log grows.
    """
    if not revs:
        return {}
    payload = "".join("{}:{}\n".format(rev, path) for rev in revs)
    proc = subprocess.run(
        ["git", "-C", repo, "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        input=payload.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    result = {}
    lines = proc.stdout.decode("utf-8", "replace").splitlines()
    for rev, line in zip(revs, lines):
        parts = line.split()
        result[rev] = parts[0] if len(parts) >= 2 and parts[1] == "blob" else None
    return result


def blob_contents(repo, shas):
    """{sha: text} for the given blob shas, in a single git call."""
    shas = [s for s in dict.fromkeys(shas) if s]
    if not shas:
        return {}
    payload = "".join(sha + "\n" for sha in shas)
    proc = subprocess.run(
        ["git", "-C", repo, "cat-file", "--batch"],
        input=payload.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    data = proc.stdout
    result, offset = {}, 0
    while offset < len(data):
        end = data.find(b"\n", offset)
        if end == -1:
            break
        header = data[offset:end].decode("utf-8", "replace").split()
        offset = end + 1
        if len(header) < 3:
            continue
        sha, size = header[0], int(header[2])
        result[sha] = data[offset:offset + size].decode("utf-8", "replace")
        offset += size + 1
    return result


def lines_of(text):
    if text is None:
        return None
    return [ln for ln in text.split("\n") if ln.strip()]


# --- check 1: append-only ------------------------------------------------------


def check_append_only(repo, ledger_dir, files):
    """No commit may change or drop a line that one of its parents already wrote.

    This is the one check that does not trust the agent at all: it reads the
    object history, not the working tree.

    Two rules, because a commit with two parents is a different situation from
    one with a single parent:

    * **One parent** — the parent's lines must be a *prefix* of the child's.
      Nothing rewritten, nothing removed, nothing inserted in the middle. This
      is the ordinary case and the strictest statement available.
    * **A merge** — every line in *every* parent must still be present in the
      child, counted with multiplicity. Order is not required, because a merge
      of two independent appends legitimately interleaves them. What is required
      is that nothing was dropped in the resolution, which is precisely the way
      a concurrent write loses data.

    The limits, stated plainly: this catches editing, not history rewriting. A
    force-push that discards commits leaves nothing to compare. And it cannot
    detect a line that was *never written* — an omission leaves no trace
    anywhere, which is why the mechanism is paired with a lock rather than
    relied on alone.
    """
    failures = []
    try:
        graph = commit_graph(repo)
    except RuntimeError as exc:
        return [Failure(CHECK_APPEND_ONLY, "(history)", str(exc))]

    revs = []
    for sha, parents in graph:
        revs.append(sha)
        revs.extend(parents)
    revs = list(dict.fromkeys(revs))

    for name in files:
        path = "{}/{}".format(ledger_dir, name) if ledger_dir else name
        shas = blob_shas(repo, revs, path)
        contents = blob_contents(repo, shas.values())

        def lines_at(rev):
            sha = shas.get(rev)
            return lines_of(contents.get(sha)) if sha else None

        for sha, parents in graph:
            child = lines_at(sha)
            for parent in parents:
                before = lines_at(parent)
                if before is None:
                    continue
                if child is None:
                    failures.append(Failure(
                        CHECK_APPEND_ONLY, "{} @ {}".format(path, sha[:8]),
                        "file was deleted; parent {} held {} line(s)".format(parent[:8], len(before))))
                    continue
                if len(parents) == 1:
                    problem = prefix_violation(before, child)
                    if problem:
                        failures.append(Failure(
                            CHECK_APPEND_ONLY, "{} @ {}".format(path, sha[:8]), problem))
                else:
                    missing = missing_lines(before, child)
                    if missing:
                        failures.append(Failure(
                            CHECK_APPEND_ONLY, "{} @ {} (merge)".format(path, sha[:8]),
                            "{} line(s) from parent {} did not survive the merge\n"
                            "        first lost: {}".format(
                                len(missing), parent[:8], trim(missing[0]))))
    return failures


def prefix_violation(before, after):
    """None if `before` is a prefix of `after`, else a description of the break."""
    if len(after) < len(before):
        return "line count fell {} -> {}".format(len(before), len(after))
    for i, old in enumerate(before):
        if after[i] != old:
            return ("existing line {} was rewritten\n        was: {}\n        now: {}"
                    .format(i + 1, trim(old), trim(after[i])))
    return None


def missing_lines(before, after):
    """Lines of `before` that `after` does not contain, counted with multiplicity."""
    from collections import Counter
    remaining = Counter(after)
    lost = []
    for line in before:
        if remaining[line] > 0:
            remaining[line] -= 1
        else:
            lost.append(line)
    return lost


def trim(s, n=110):
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# --- reading rows --------------------------------------------------------------


def read_rows(root, ledger_dir, name):
    """Parse one JSONL file from the working tree. Returns (rows, failures)."""
    path = os.path.join(root, ledger_dir, name) if ledger_dir else os.path.join(root, name)
    rows, failures = [], []
    if not os.path.exists(path):
        return rows, failures
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append((lineno, json.loads(line)))
            except ValueError as exc:
                failures.append(
                    Failure("parse", "{}/{} line {}".format(ledger_dir, name, lineno), str(exc))
                )
    return rows, failures


# --- check 2: every external act names a claim ---------------------------------


def check_external(root, ledger_dir):
    """An act that reached the outside world with no claim behind it is the
    failure this whole ledger exists to catch."""
    rows, failures = read_rows(root, ledger_dir, "external.jsonl")
    for lineno, row in rows:
        if not row.get("claim_id"):
            failures.append(
                Failure(
                    CHECK_EXTERNAL_CLAIMED,
                    "external.jsonl line {}".format(lineno),
                    "claim_id is null: {}".format(trim(row.get("what", "(no description)"))),
                )
            )
    return failures


# --- check 3: the wallet balance adds up ---------------------------------------


def check_balance(root, ledger_dir, initial_balance):
    """`balance` on each row must equal initial minus every `out` so far.

    Money coming *in* lands in the human's account, not in the agent's wallet,
    so it does not move this number. Keeping them apart is deliberate: it stops
    "we earned it" from arriving before the money does.
    """
    rows, failures = read_rows(root, ledger_dir, "money.jsonl")
    spent = 0
    for lineno, row in rows:
        direction = row.get("dir")
        if direction == "out":
            try:
                spent += int(row.get("amount") or 0)
            except (TypeError, ValueError):
                failures.append(
                    Failure(CHECK_BALANCE, "money.jsonl line {}".format(lineno),
                            "amount is not a number: {!r}".format(row.get("amount")))
                )
                continue
        expected = initial_balance - spent
        stated = row.get("balance")
        if stated is None:
            failures.append(
                Failure(CHECK_BALANCE, "money.jsonl line {}".format(lineno), "balance is missing")
            )
        elif stated != expected:
            failures.append(
                Failure(
                    CHECK_BALANCE,
                    "money.jsonl line {}".format(lineno),
                    "balance says {} but running total is {}".format(stated, expected),
                )
            )
    return failures


# --- check 4: no prediction outlives its deadline unresolved --------------------


def parse_ts(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def check_predictions(root, ledger_dir, now):
    """A prediction left "unresolved" past its own deadline is not a prediction
    any more. It is an excuse. This is the check an agent will most want to skip,
    which is exactly why it is mechanical."""
    rows, failures = read_rows(root, ledger_dir, "predictions.jsonl")

    # "The last row wins" is resolved by the row's own timestamp, not by its
    # position in the file. A merge of two concurrent appends may interleave
    # them, and if position decided the winner, a merge could silently change
    # which state a prediction is in. Position is only the tie-breaker.
    latest = {}
    for lineno, row in rows:
        pred_id = row.get("pred_id")
        if not pred_id:
            failures.append(
                Failure(CHECK_PREDICTIONS, "predictions.jsonl line {}".format(lineno),
                        "row has no pred_id")
            )
            continue
        key = (parse_ts(row.get("ts")) or datetime.min.replace(tzinfo=timezone.utc), lineno)
        if pred_id not in latest or key > latest[pred_id][0]:
            latest[pred_id] = (key, lineno, row)
    latest = {pid: (lineno, row) for pid, (_, lineno, row) in latest.items()}

    for pred_id, (lineno, row) in sorted(latest.items()):
        if not row.get("x") or not row.get("deadline"):
            failures.append(
                Failure(
                    CHECK_PREDICTIONS,
                    "predictions.jsonl line {} ({})".format(lineno, pred_id),
                    "a prediction with no X or no deadline does not count as one",
                )
            )
            continue
        deadline = parse_ts(row.get("deadline"))
        if deadline is None:
            failures.append(
                Failure(CHECK_PREDICTIONS, "predictions.jsonl line {} ({})".format(lineno, pred_id),
                        "deadline is not an ISO 8601 timestamp: {!r}".format(row.get("deadline")))
            )
            continue
        unresolved = row.get("result") in (None, "", "未確定", "unresolved", "pending")
        if unresolved and deadline < now:
            failures.append(
                Failure(
                    CHECK_PREDICTIONS,
                    "predictions.jsonl line {} ({})".format(lineno, pred_id),
                    "deadline {} has passed and the result is still unresolved".format(
                        row.get("deadline")
                    ),
                )
            )
    return failures


# --- driver --------------------------------------------------------------------

LEDGER_FILES = [
    "money.jsonl",
    "human.jsonl",
    "claims.jsonl",
    "external.jsonl",
    "rules.jsonl",
    "predictions.jsonl",
]

CHECK_TITLES = [
    (CHECK_APPEND_ONLY, "no committed ledger line was ever rewritten or dropped"),
    (CHECK_EXTERNAL_CLAIMED, "every act that reached the outside names the claim behind it"),
    (CHECK_BALANCE, "the stated wallet balance matches the recorded spending"),
    (CHECK_PREDICTIONS, "no prediction is sitting past its deadline unresolved"),
]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify an append-only agent ledger.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit status: 0 all checks pass, 1 a check failed, 2 bad usage.",
    )
    parser.add_argument("--repo", default=".", help="git repository holding the ledger (default: .)")
    parser.add_argument("--ledger", default="audit", help="ledger directory inside the repo (default: audit)")
    parser.add_argument("--initial-balance", type=int, default=1000,
                        help="starting wallet balance for the balance check (default: 1000)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit JSON instead of prose")
    parser.add_argument("--now", default=None,
                        help="ISO 8601 instant to evaluate deadlines against (default: now, UTC)")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(root, ".git")):
        parser.error("{} is not a git repository (the append-only check reads git history)".format(root))
    ledger_path = os.path.join(root, args.ledger) if args.ledger else root
    if not os.path.isdir(ledger_path):
        parser.error("ledger directory not found: {}".format(ledger_path))

    now = parse_ts(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        parser.error("--now is not an ISO 8601 timestamp: {!r}".format(args.now))

    present = [name for name in LEDGER_FILES if os.path.exists(os.path.join(ledger_path, name))]

    # An unborn HEAD is not evidence of good behaviour, and it is not evidence
    # of tampering either. Check 1 has nothing to read, so it is reported as
    # inapplicable rather than passed — saying "pass" here would be the exact
    # kind of unearned reassurance this tool exists to avoid.
    history_available = has_commits(root)

    failures = []
    if history_available:
        failures += check_append_only(root, args.ledger, present)
    failures += check_external(root, args.ledger)
    failures += check_balance(root, args.ledger, args.initial_balance)
    failures += check_predictions(root, args.ledger, now)

    by_check = {}
    for failure in failures:
        by_check.setdefault(failure.check, []).append(failure)

    if args.as_json:
        print(json.dumps(
            {
                "checked_at": now.isoformat().replace("+00:00", "Z"),
                "repo": root,
                "ledger": args.ledger,
                "files_present": present,
                "append_only_applicable": history_available,
                "ok": not failures,
                "failures": [f.as_dict() for f in failures],
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 1 if failures else 0

    print("ledger: {}/{}  ({} of {} files present)".format(
        os.path.basename(root), args.ledger, len(present), len(LEDGER_FILES)))
    print("as of: {}\n".format(now.isoformat().replace("+00:00", "Z")))
    for check, title in CHECK_TITLES:
        hits = by_check.get(check, [])
        if check == CHECK_APPEND_ONLY and not history_available:
            print("n/a   {}\n      nothing is committed yet, so there is no history to check".format(title))
            continue
        print("{}  {}".format("FAIL" if hits else "pass", title))
        for failure in hits:
            print(failure)
    parse_errors = by_check.get("parse", [])
    if parse_errors:
        print("FAIL  every ledger line parses as JSON")
        for failure in parse_errors:
            print(failure)
    print()
    print("{} check(s) failed.".format(len(failures)) if failures else "All checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        sys.exit(2)
