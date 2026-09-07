#!/usr/bin/env python3
"""
selftest.py — does verify.py actually catch anything?

A verifier that has only ever printed "pass" has demonstrated nothing. This
builds a throwaway git repository, breaks the ledger in each of the four ways
the checks are supposed to notice, and asserts that each one fires.

    python3 selftest.py

Exit 0 if every check both fires when it should and stays quiet when it should.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
VERIFY = os.path.join(HERE, "verify.py")

CLEAN = {
    "money.jsonl": [
        {"ts": "2026-01-01T00:00:00Z", "dir": "out", "amount": 100, "via": "card",
         "what": "a domain", "evidence": "receipts/1.png", "claim_id": "C-0001", "balance": 900},
    ],
    "external.jsonl": [
        {"ts": "2026-01-01T00:00:00Z", "what": "published a page", "where": "the web",
         "reversible": False, "claim_id": "C-0001"},
    ],
    "predictions.jsonl": [
        {"ts": "2026-01-01T00:00:00Z", "pred_id": "P-0001", "x": "someone who is not me opens an issue",
         "why_not_me": "I cannot open issues as another account",
         "deadline": "2026-01-10T00:00:00Z", "result": "unresolved",
         "result_ts": None, "evidence": None},
    ],
}

NOW_BEFORE_DEADLINE = "2026-01-05T00:00:00Z"
NOW_AFTER_DEADLINE = "2026-02-01T00:00:00Z"


def run(*args, **kwargs):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def git(repo, *args):
    code, out = run("git", "-C", repo, *args)
    if code != 0:
        raise RuntimeError("git {} failed:\n{}".format(" ".join(args), out))


def write_ledger(repo, rows_by_file):
    ledger = os.path.join(repo, "audit")
    os.makedirs(ledger, exist_ok=True)
    for name, rows in rows_by_file.items():
        with open(os.path.join(ledger, name), "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_repo(rows_by_file):
    repo = tempfile.mkdtemp(prefix="ledger-selftest-")
    git(repo, "init", "-q", ".")
    git(repo, "config", "user.email", "selftest@example.invalid")
    git(repo, "config", "user.name", "selftest")
    git(repo, "config", "commit.gpgsign", "false")
    write_ledger(repo, rows_by_file)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial ledger")
    return repo


def verify(repo, now):
    code, out = run(sys.executable, VERIFY, "--repo", repo, "--ledger", "audit",
                    "--initial-balance", "1000", "--now", now, "--json")
    return code, json.loads(out)


def deep_copy(rows_by_file):
    return json.loads(json.dumps(rows_by_file))


def case_clean(repo):
    """Nothing broken: every check must stay quiet."""
    return None


def case_rewritten_line(repo):
    """Check 1: edit a line that is already committed."""
    rows = deep_copy(CLEAN)
    rows["money.jsonl"][0]["amount"] = 300
    write_ledger(repo, rows)
    git(repo, "commit", "-qam", "quietly fix yesterday's number")
    return "append_only"


def case_dropped_line(repo):
    """Check 1 again: delete a committed line rather than editing it."""
    rows = deep_copy(CLEAN)
    rows["money.jsonl"] = []
    write_ledger(repo, rows)
    git(repo, "commit", "-qam", "tidy up")
    return "append_only"


def case_unclaimed_external(repo):
    """Check 2: reach the outside world with nothing authorising it."""
    with open(os.path.join(repo, "audit", "external.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2026-01-03T00:00:00Z", "what": "emailed 400 strangers",
                             "where": "smtp", "reversible": False, "claim_id": None},
                            ensure_ascii=False) + "\n")
    git(repo, "commit", "-qam", "log an external act")
    return "external_has_claim"


def case_balance_drift(repo):
    """Check 3: spend money and state a balance that does not follow."""
    with open(os.path.join(repo, "audit", "money.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2026-01-03T00:00:00Z", "dir": "out", "amount": 50,
                             "via": "card", "what": "hosting", "evidence": None,
                             "claim_id": "C-0002", "balance": 880}, ensure_ascii=False) + "\n")
    git(repo, "commit", "-qam", "log a payment")
    return "balance_consistent"


def case_stale_prediction(repo):
    """Check 4: let a deadline pass with the result still open.

    Nothing is written here — the violation is the passage of time, which is
    what makes it the easiest one to not notice.
    """
    return "predictions_resolved"


CASES = [
    ("a clean ledger raises nothing", case_clean, NOW_BEFORE_DEADLINE),
    ("an edited committed line", case_rewritten_line, NOW_BEFORE_DEADLINE),
    ("a deleted committed line", case_dropped_line, NOW_BEFORE_DEADLINE),
    ("an external act with no claim", case_unclaimed_external, NOW_BEFORE_DEADLINE),
    ("a balance that does not follow from the spending", case_balance_drift, NOW_BEFORE_DEADLINE),
    ("a prediction past its deadline", case_stale_prediction, NOW_AFTER_DEADLINE),
]


def case_no_history():
    """A repository with nothing committed yet must not be reported as tampered.

    "There is no history" and "the history was altered" are opposite findings.
    Conflating them makes the first push of any ledger look like a violation.
    """
    repo = tempfile.mkdtemp(prefix="ledger-selftest-")
    try:
        git(repo, "init", "-q", ".")
        git(repo, "config", "user.email", "selftest@example.invalid")
        git(repo, "config", "user.name", "selftest")
        write_ledger(repo, CLEAN)
        code, result = verify(repo, NOW_BEFORE_DEADLINE)
        fired = {f["check"] for f in result["failures"]}
        ok = "append_only" not in fired and result["append_only_applicable"] is False and code == 0
        detail = "expected append_only to be reported inapplicable, got fired={} applicable={} exit={}".format(
            sorted(fired), result.get("append_only_applicable"), code)
        print("{}  {}".format("ok  " if ok else "FAIL", "an unborn HEAD is not a violation"))
        return None if ok else "an unborn HEAD is not a violation: " + detail
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def main():
    failures = []
    for title, mutate, now in CASES:
        repo = make_repo(CLEAN)
        try:
            expected = mutate(repo)
            code, result = verify(repo, now)
            fired = {f["check"] for f in result["failures"]}

            if expected is None:
                ok = result["ok"] and code == 0
                detail = "expected a clean pass, got: {}".format(sorted(fired) or "exit {}".format(code))
            else:
                ok = expected in fired and code == 1
                detail = "expected check {!r} to fire, fired: {}".format(expected, sorted(fired) or "nothing")

            print("{}  {}".format("ok  " if ok else "FAIL", title))
            if not ok:
                failures.append("{}: {}".format(title, detail))
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    extra = case_no_history()
    if extra:
        failures.append(extra)

    print()
    if failures:
        for line in failures:
            print("  " + line)
        print("\n{} self-test(s) failed. verify.py is not checking what it claims to.".format(len(failures)))
        return 1
    print("verify.py handles all {} cases.".format(len(CASES) + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
