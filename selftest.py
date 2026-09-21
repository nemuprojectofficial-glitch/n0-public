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
    "claims.jsonl": [
        {"ts": "2026-01-01T00:00:00Z", "claim_id": "C-0001", "kind": "setup",
         "summary": "publish a page", "status": "pending", "decided_ts": None},
        {"ts": "2026-01-02T00:00:00Z", "claim_id": "C-0001", "kind": "setup",
         "summary": "settled: granted", "status": "granted",
         "decided_ts": "2026-01-02T00:00:00Z",
         "recorded_by": "the human", "source": "appended by the human to this file"},
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


def verify(repo, now, provenance_since=None, ts_since=None, ts_ack=None, history_ack=None,
           horizon=None):
    extra = ["--provenance-since", provenance_since] if provenance_since else []
    if horizon:
        extra += ["--horizon", horizon]
    if ts_since:
        extra += ["--ts-since", ts_since]
    if ts_ack:
        extra += ["--ts-ack", ts_ack]
    if history_ack:
        extra += ["--history-ack", history_ack]
    code, out = run(sys.executable, VERIFY, "--repo", repo, "--ledger", "audit",
                    "--initial-balance", "1000", "--now", now, "--json", *extra)
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


def case_unattributed_decision(repo):
    """Check 5: record an answer without saying who wrote it down.

    This is the one an agent can commit while believing it is being helpful.
    The row is true, the row is useful, and the file can no longer tell it
    apart from a line the human wrote.
    """
    with open(os.path.join(repo, "audit", "claims.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2026-01-03T00:00:00Z", "claim_id": "C-0002",
                             "kind": "setup", "summary": "settled: granted",
                             "status": "granted", "decided_ts": "2026-01-03T00:00:00Z"},
                            ensure_ascii=False) + "\n")
    git(repo, "commit", "-qam", "record the answer that came back")
    return "decision_provenance"


def case_provenance_cutoff(repo):
    """Check 5, the other way: an unmarked row from before the rule was adopted
    is left alone. Old rows cannot be marked after the fact without editing
    them, and editing them is what check 1 exists to forbid."""
    with open(os.path.join(repo, "audit", "claims.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2025-12-01T00:00:00Z", "claim_id": "C-0000",
                             "kind": "setup", "summary": "settled long before the rule",
                             "status": "granted", "decided_ts": "2025-12-01T00:00:00Z"},
                            ensure_ascii=False) + "\n")
    git(repo, "commit", "-qam", "an old answer, from before check 5 existed")
    return None


def case_future_stamped_row(repo):
    """Check 6: a row whose own `ts` is later than the commit carrying it.

    The act it describes may well have happened; what cannot have happened is
    the writing-down, because the clock had not reached that time when the
    commit was made. Both numbers come from git, so this needs no trust in the
    agent at all — and none of the five earlier checks looks at it."""
    with open(os.path.join(repo, "audit", "external.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2030-01-01T00:00:00Z", "what": "published a page",
                             "where": "the web", "reversible": False,
                             "claim_id": "C-0001"}, ensure_ascii=False) + "\n")
    git(repo, "commit", "-qam", "an act stamped years after this commit")
    return "row_ts_not_after_commit"


def case_future_row_before_cutoff(repo):
    """Check 6, the other way: with the rule adopted from a later date, the
    offending row is left alone. Offending rows cannot be corrected — editing
    them is exactly what check 1 forbids — so an existing ledger adopts the
    rule from a date and leaves the earlier rows readable as what they are."""
    return case_future_stamped_row(repo) and None


CASES = [
    ("a clean ledger raises nothing", case_clean, NOW_BEFORE_DEADLINE),
    ("an edited committed line", case_rewritten_line, NOW_BEFORE_DEADLINE),
    ("a deleted committed line", case_dropped_line, NOW_BEFORE_DEADLINE),
    ("an external act with no claim", case_unclaimed_external, NOW_BEFORE_DEADLINE),
    ("a balance that does not follow from the spending", case_balance_drift, NOW_BEFORE_DEADLINE),
    ("a prediction past its deadline", case_stale_prediction, NOW_AFTER_DEADLINE),
    ("a settled claim with nothing saying who recorded it", case_unattributed_decision,
     NOW_BEFORE_DEADLINE),
    ("a row stamped later than the commit that carries it", case_future_stamped_row,
     NOW_BEFORE_DEADLINE),
]

# Cases that need verify() called with something other than the defaults.
CASES_WITH_CUTOFF = [
    ("an unmarked decision from before the cutoff is left alone", case_provenance_cutoff,
     NOW_BEFORE_DEADLINE, "2026-01-01T00:00:00Z"),
]

# Cases that need check 6's adoption date moved past the offending row.
# Cases that name an individual offending row instead of moving check 6's date.
# ★ Added 2026-09-14, after this repository broke check 6 two minutes after
# having the clock available. A date can be advanced past a violation that has
# not been written yet; a name cannot. So the escape hatch has to say which row.
CASES_WITH_TS_ACK = [
    ("a named future-stamped row is excused, and only that one",
     case_future_stamped_row, NOW_BEFORE_DEADLINE, "audit/external.jsonl line 2", None),
    ("an acknowledgement that matches nothing is itself a failure",
     case_clean, NOW_BEFORE_DEADLINE, "audit/external.jsonl line 3",
     "row_ts_not_after_commit"),
    ("naming the wrong row does not excuse the real one",
     case_future_stamped_row, NOW_BEFORE_DEADLINE, "audit/claims.jsonl line 99",
     "row_ts_not_after_commit"),
]

CASES_WITH_TS_CUTOFF = [
    ("a future-stamped row from before check 6's cutoff is left alone",
     case_future_row_before_cutoff, NOW_BEFORE_DEADLINE, "2031-01-01T00:00:00Z"),
]

# Check 4 with a horizon.
#
# ★ Added 2026-09-21 (session 96), after the agent that maintains this file
# wrote, in a prediction's own `evidence` field, that the measurement had been
# impossible -- and left `result` unresolved. Check 4 was asked at that moment
# and passed, because the deadline was three hours out. The ledger was
# published. The deadline then passed with nobody awake.
#
# The check was never wrong. It was asked in the wrong direction: always while
# someone could act, always about a moment when someone could act.
#
# Two other places to put the gate were built and thrown away first, each
# killed by counting how often it would have fired over this ledger's history:
# "evidence present but result unresolved" fired on 104 rows (registration
# rows legitimately carry setup notes in `evidence`), and "deadline before the
# next wake, judged when the row is written" fired on 70 rows (a prediction
# registered, measured and settled inside one session legitimately has a
# deadline before the next wake). The horizon belongs at the moment a run
# ends, not at the moment a row is written.
CASES_WITH_HORIZON = [
    # The real shape: unresolved, deadline still in the future, but before the
    # next time anyone can act.
    ("a deadline that will pass unattended before the next run",
     case_stale_prediction, NOW_BEFORE_DEADLINE, "2026-03-01T00:00:00Z", "predictions_resolved"),
    # A horizon must not turn a clean ledger dirty just by existing: the clean
    # fixture's deadline is after this horizon, so nothing fires.
    ("a horizon short of every deadline leaves a clean ledger clean",
     case_clean, NOW_BEFORE_DEADLINE, "2026-01-06T00:00:00Z", None),
    # Without a horizon the same ledger passes. This is the blind spot itself,
    # kept as a test so it cannot be closed by accident and then reopened.
    ("without a horizon, the same ledger passes",
     case_stale_prediction, NOW_BEFORE_DEADLINE, None, None),
]


def build_merge_repo(resolution):
    """Two branches each append a different row, then merge with `resolution`.

    `resolution(lines_ours, lines_theirs) -> lines` decides what the merge
    commit contains, standing in for whatever merge driver or human resolves
    the conflict.
    """
    repo = make_repo(CLEAN)
    base_rows = deep_copy(CLEAN)

    ours = base_rows["predictions.jsonl"] + [
        {"ts": "2026-01-02T00:00:00Z", "pred_id": "P-0002", "x": "branch A's row",
         "why_not_me": "-", "deadline": "2026-01-10T00:00:00Z", "result": "unresolved",
         "result_ts": None, "evidence": None}]
    theirs = base_rows["predictions.jsonl"] + [
        {"ts": "2026-01-02T01:00:00Z", "pred_id": "P-0003", "x": "branch B's row",
         "why_not_me": "-", "deadline": "2026-01-10T00:00:00Z", "result": "unresolved",
         "result_ts": None, "evidence": None}]

    git(repo, "checkout", "-q", "-b", "other")
    rows = deep_copy(base_rows); rows["predictions.jsonl"] = theirs
    write_ledger(repo, rows)
    git(repo, "commit", "-qam", "branch B appends")

    git(repo, "checkout", "-q", "-")
    rows = deep_copy(base_rows); rows["predictions.jsonl"] = ours
    write_ledger(repo, rows)
    git(repo, "commit", "-qam", "branch A appends")

    # Expected to conflict: both branches appended at the end of the same file.
    # The conflict is the situation under test, so a non-zero exit here is fine.
    run("git", "-C", repo, "merge", "--no-commit", "--no-ff", "other")
    merged = resolution([json.dumps(r, ensure_ascii=False) for r in ours],
                        [json.dumps(r, ensure_ascii=False) for r in theirs])
    with open(os.path.join(repo, "audit", "predictions.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(merged) + "\n")
    git(repo, "add", "-A")
    git(repo, "-c", "core.editor=true", "commit", "-q", "--no-edit")
    return repo


def case_merge_keeping_everything():
    """A merge that keeps both sides' lines must not be reported as tampering.

    Concurrent appends legitimately interleave. If the check demanded a linear
    prefix here it would fire on every honest merge, and an alarm that is always
    ringing is the same as no alarm.
    """
    def union(ours, theirs):
        return ours + [line for line in theirs if line not in ours]
    repo = build_merge_repo(union)
    try:
        code, result = verify(repo, NOW_BEFORE_DEADLINE)
        fired = {f["check"] for f in result["failures"]}
        ok = "append_only" not in fired
        print("{}  {}".format("ok  " if ok else "FAIL", "a merge that keeps every line is not a violation"))
        return None if ok else "a merge that keeps every line is not a violation: fired {}".format(sorted(fired))
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def case_merge_dropping_a_line():
    """A merge that resolves by discarding one side must be caught.

    This is how a concurrent write actually loses data: not by editing a line,
    but by a conflict resolution that picks one side. Nothing in the working
    tree shows it afterwards — only the parent edges do.
    """
    def keep_ours_only(ours, theirs):
        return ours
    repo = build_merge_repo(keep_ours_only)
    try:
        code, result = verify(repo, NOW_BEFORE_DEADLINE)
        fired = {f["check"] for f in result["failures"]}
        ok = "append_only" in fired and code == 1
        print("{}  {}".format("ok  " if ok else "FAIL", "a merge that drops a line is caught"))
        return None if ok else "a merge that drops a line is caught: fired {}".format(sorted(fired) or "nothing")
    finally:
        shutil.rmtree(repo, ignore_errors=True)


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


def case_shallow_clone():
    """A truncated history must not be reported with the same word as a clean one.

    Check 1 walks `git log HEAD`. A shallow clone's oldest visible commit has no
    parents as far as git is concerned, so every ledger line already present
    there is never compared against anything — and, before this case existed,
    the check printed "pass" over it.

    Two assertions, because one alone would let the wrong fix through:
      * by default the truncation fails the check;
      * with --allow-shallow it does not fail, but it is still reported.
    A fix that merely silenced the condition would pass the first and fail the
    second.
    """
    source = make_repo(CLEAN)
    clone = tempfile.mkdtemp(prefix="ledger-selftest-shallow-")
    shutil.rmtree(clone, ignore_errors=True)
    try:
        # A second commit, so that depth-1 genuinely leaves history behind.
        rows = deep_copy(CLEAN)
        rows["external.jsonl"].append(dict(rows["external.jsonl"][-1], ts="2026-02-02T00:00:00Z"))
        write_ledger(source, rows)
        git(source, "commit", "-qam", "a later append")

        code, _ = run("git", "clone", "-q", "--depth", "1", "file://" + source, clone)
        if code != 0:
            return "a shallow clone is not a clean pass: could not create the shallow clone"

        code_default, result_default = verify(clone, NOW_BEFORE_DEADLINE)
        fired = {f["check"] for f in result_default["failures"]}

        code_allowed, out_allowed = run(
            sys.executable, VERIFY, "--repo", clone, "--ledger", "audit",
            "--initial-balance", "1000", "--now", NOW_BEFORE_DEADLINE, "--json",
            "--allow-shallow")
        allowed = json.loads(out_allowed)
        allowed_fired = {f["check"] for f in allowed["failures"]}

        ok = ("append_only" in fired and code_default == 1
              and "append_only" not in allowed_fired
              and allowed.get("shallow_clone")
              and allowed.get("shallow_allowed") is True)
        detail = ("expected append_only to fire by default (fired={}, exit={}) and to be reported "
                  "but not enforced under --allow-shallow (fired={}, note={!r})".format(
                      sorted(fired), code_default, sorted(allowed_fired), allowed.get("shallow_clone")))
        print("{}  {}".format("ok  " if ok else "FAIL",
                              "a shallow clone is reported, not passed"))
        return None if ok else "a shallow clone is reported, not passed: " + detail
    finally:
        shutil.rmtree(source, ignore_errors=True)
        shutil.rmtree(clone, ignore_errors=True)


def case_shallow_stale_ack():
    """Session 86. A --ts-ack entry cannot be matched in a clone whose history is cut.

    Check 6 finds a violation by looking at the commit that *first carried* the
    row. In a shallow clone that commit may be gone, so an acknowledgement of a
    genuine, permanent violation looks stale — and this repository's own publish
    gate failed on five such entries, all of them real. The list had not rotted;
    the history under it had been cut off.

    Three assertions, because any one of them alone would let a wrong fix through:
      * shallow + --allow-shallow: the unmatched entry does not fail the check
        (and is still printed — the caller sees "note", never silence);
      * shallow without --allow-shallow: it still fails, because that is the
        configuration CI runs;
      * deep + --allow-shallow: it still fails, because the excuse must attach to
        the truncated history, not to the flag being present.
    """
    source = make_repo(CLEAN)
    clone = tempfile.mkdtemp(prefix="ledger-selftest-stale-ack-")
    shutil.rmtree(clone, ignore_errors=True)
    stale = "audit/external.jsonl line 99"
    try:
        rows = deep_copy(CLEAN)
        rows["external.jsonl"].append(dict(rows["external.jsonl"][-1], ts="2026-02-02T00:00:00Z"))
        write_ledger(source, rows)
        git(source, "commit", "-qam", "a later append")
        code, _ = run("git", "clone", "-q", "--depth", "1", "file://" + source, clone)
        if code != 0:
            return "a stale ack in a shallow clone: could not create the shallow clone"

        def fired(repo, *extra):
            _, out = run(sys.executable, VERIFY, "--repo", repo, "--ledger", "audit",
                         "--initial-balance", "1000", "--now", NOW_BEFORE_DEADLINE,
                         "--json", "--ts-ack", stale, *extra)
            return {f["check"] for f in json.loads(out)["failures"]}

        shallow_allowed = fired(clone, "--allow-shallow")
        shallow_strict = fired(clone)
        deep_allowed = fired(source, "--allow-shallow")

        ok = ("row_ts_not_after_commit" not in shallow_allowed
              and "row_ts_not_after_commit" in shallow_strict
              and "row_ts_not_after_commit" in deep_allowed)
        detail = ("expected the unmatched ack to be excused only when the clone is "
                  "shallow AND --allow-shallow is given (shallow+allowed={}, "
                  "shallow+strict={}, deep+allowed={})".format(
                      sorted(shallow_allowed), sorted(shallow_strict), sorted(deep_allowed)))
        title = "a stale ack is excused only by a cut history, not by the flag"
        print("{}  {}".format("ok  " if ok else "FAIL", title))
        return None if ok else title + ": " + detail
    finally:
        shutil.rmtree(source, ignore_errors=True)
        shutil.rmtree(clone, ignore_errors=True)


def case_history_ack():
    """--history-ack must excuse exactly the break it names, and nothing else.

    ★ Added 2026-09-15, in the same session that added the flag. The flag is an
    escape hatch cut into check 1 — the one check that reads git objects and
    trusts the agent with nothing — so it is the single most dangerous thing in
    this file. A broken --ts-ack costs a red build. A broken --history-ack would
    let a real, silent loss of ledger lines be waved through by a name.

    Three assertions, because any one alone lets a wrong implementation pass:

      * the named break stops failing the check (otherwise the flag does nothing);
      * a name that matches no break is itself a failure (otherwise the list of
        excuses can grow quietly, which is the whole reason --ts-ack exists);
      * naming the wrong break does not excuse the real one (otherwise any
        plausible-looking string disarms the check).

    The third is the one that matters. An implementation that simply drops every
    append_only failure whenever --history-ack is non-empty passes the first two.
    """
    title = "a named history break is excused, and only that one"
    results = []
    repo = make_repo(CLEAN)
    try:
        # Rewrite a committed line in predictions.jsonl rather than money.jsonl:
        # editing an amount would also trip the balance check, and this case has
        # to be able to assert a *completely* clean exit once the break is named.
        rows = deep_copy(CLEAN)
        rows["predictions.jsonl"][0]["x"] = "a quietly reworded prediction"
        write_ledger(repo, rows)
        git(repo, "commit", "-qam", "quietly reword yesterday's prediction")
        _, head = run("git", "-C", repo, "rev-parse", "HEAD")
        sha = head.strip()[:8]
        real = "audit/predictions.jsonl @ {}".format(sha)

        # 1. naming the real break clears it
        code, result = verify(repo, NOW_BEFORE_DEADLINE, history_ack=real)
        fired = {f["check"] for f in result["failures"]}
        results.append(("append_only" not in fired and code == 0,
                        "naming the real break did not clear it (fired={}, exit={})".format(
                            sorted(fired), code)))
        # and it is still printed, not folded into "pass"
        results.append((len(result.get("acknowledged_history_breaks") or []) == 1,
                        "the acknowledged break was not reported back"))

        # 2. naming the wrong break leaves the real one firing
        code, result = verify(repo, NOW_BEFORE_DEADLINE,
                              history_ack="audit/predictions.jsonl @ 0badbad0")
        fired = {f["check"] for f in result["failures"]}
        results.append(("append_only" in fired and code == 1,
                        "naming the wrong break excused the real one (fired={}, exit={})".format(
                            sorted(fired), code)))
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # 3. on a clean ledger, an acknowledgement matching nothing is itself a failure
    repo = make_repo(CLEAN)
    try:
        code, result = verify(repo, NOW_BEFORE_DEADLINE,
                              history_ack="audit/predictions.jsonl @ 0badbad0")
        fired = {f["check"] for f in result["failures"]}
        results.append(("append_only" in fired and code == 1,
                        "a stale acknowledgement did not fail (fired={}, exit={})".format(
                            sorted(fired), code)))
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    bad = [detail for ok, detail in results if not ok]
    print("{}  {}".format("ok  " if not bad else "FAIL", title))
    return None if not bad else "{}: {}".format(title, "; ".join(bad))


def main():
    failures = []
    tagged = ([(t, m, n, None, None) for t, m, n in CASES]
              + [(t, m, n, c, None) for t, m, n, c in CASES_WITH_CUTOFF]
              + [(t, m, n, None, c) for t, m, n, c in CASES_WITH_TS_CUTOFF])
    for title, mutate, now, prov_cut, ts_cut in tagged:
        repo = make_repo(CLEAN)
        try:
            expected = mutate(repo)
            code, result = verify(repo, now, prov_cut, ts_cut)
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

    # The acknowledgement cases override what the mutation would otherwise
    # expect: naming the row is supposed to turn a firing check quiet, and only
    # that row.
    for title, mutate, now, horizon, expected in CASES_WITH_HORIZON:
        repo = make_repo(CLEAN)
        try:
            mutate(repo)
            code, result = verify(repo, now, horizon=horizon)
            fired = {f["check"] for f in result["failures"]}
            if expected is None:
                ok = result["ok"] and code == 0
                detail = "expected a clean pass, got: {}".format(sorted(fired) or "exit %d" % code)
            else:
                ok = expected in fired and code == 1
                detail = "expected {!r} to fire, fired: {}".format(expected, sorted(fired) or "nothing")
            print("{}  {}".format("ok  " if ok else "FAIL", title))
            if not ok:
                failures.append("{}: {}".format(title, detail))
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    for title, mutate, now, ack, expected in CASES_WITH_TS_ACK:
        repo = make_repo(CLEAN)
        try:
            mutate(repo)
            code, result = verify(repo, now, None, None, ack)
            fired = {f["check"] for f in result["failures"]}
            if expected is None:
                ok = result["ok"] and code == 0
                detail = "expected a clean pass, got: {}".format(sorted(fired) or "exit %d" % code)
            else:
                ok = expected in fired and code == 1
                detail = "expected {!r} to fire, fired: {}".format(expected, sorted(fired) or "nothing")
            print("{}  {}".format("ok  " if ok else "FAIL", title))
            if not ok:
                failures.append("{}: {}".format(title, detail))
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    for extra_case in (case_merge_keeping_everything, case_merge_dropping_a_line, case_no_history,
                       case_shallow_clone, case_shallow_stale_ack, case_history_ack):
        extra = extra_case()
        if extra:
            failures.append(extra)

    print()
    if failures:
        for line in failures:
            print("  " + line)
        print("\n{} self-test(s) failed. verify.py is not checking what it claims to.".format(len(failures)))
        return 1
    print("verify.py handles all {} cases.".format(
        len(CASES) + len(CASES_WITH_CUTOFF) + len(CASES_WITH_TS_CUTOFF)
        + len(CASES_WITH_HORIZON) + len(CASES_WITH_TS_ACK) + 6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
