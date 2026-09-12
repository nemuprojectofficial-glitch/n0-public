#!/usr/bin/env python3
"""release_freeze.py — refuse to publish while an open prediction depends on not publishing.

No dependencies. Python 3.8+. Reads the ledger, writes nothing.

Why this exists
---------------
Some measurements are destroyed by the act of publishing. The first day after a
release, nearly every download of a package is automation that fetches whatever
appeared on PyPI that minute. So the only way to find out whether anybody is
actually installing a thing is to *stop releasing it* and watch what happens to
the numbers on the days that have no release in them.

That makes "do not publish until this date" part of the measurement, not a mood.
And a rule that lives only in a note gets broken by whoever reads the note next
and is in a hurry — which here is me, tomorrow, with no memory of writing it.

So the freeze is a row in the append-only ledger, and this script is what the
publishing workflow runs before it builds anything:

    python3 release_freeze.py --ledger audit --target pypi:agent-audit-ledger
        exit 0  nothing open is asking for silence
        exit 1  a freeze is in force; it prints which prediction and until when
        exit 2  bad usage

Declaring one
-------------
Append a prediction row carrying a `freeze` field:

    {"pred_id": "P-0025", ..., "result": "未確定",
     "deadline": "2026-09-19T00:00:00Z",
     "freeze": "pypi:agent-audit-ledger"}

A freeze is in force only while that prediction's latest row is still open
(`result` is "未確定") and its deadline has not passed. Settling the prediction
lifts the freeze; so does the deadline. Neither requires editing anything, which
is what the ledger's append-only rule demands.

Lifting one early is allowed and is meant to be visible: append a row for the
same pred_id that settles it — including settling it as "測定不能" because you
chose to publish. What is not allowed is publishing and *then* calling the
prediction fulfilled.
"""

import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone

OPEN = "未確定"


def parse_ts(value):
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def latest_rows(path):
    """Last row per pred_id. The ledger is append-only, so a later row for the
    same id is the current state of that prediction."""
    latest = {}
    with io.open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                return None, "predictions.jsonl line %d is not JSON" % lineno
            pid = row.get("pred_id")
            if pid:
                latest[pid] = row
    return latest, None


def active_freezes(rows, target, now):
    out = []
    for pid, row in sorted(rows.items()):
        freeze = str(row.get("freeze") or "").strip()
        if not freeze or (target and freeze != target):
            continue
        if str(row.get("result") or "").strip() != OPEN:
            continue                      # settled: the freeze is lifted
        deadline = parse_ts(row.get("deadline"))
        if deadline is not None and deadline <= now:
            continue                      # expired: it is no longer asking
        out.append((pid, freeze, row.get("deadline"), row.get("x") or ""))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Refuse to publish while an open prediction requires not publishing.")
    ap.add_argument("--ledger", default="audit", help="ledger directory (default: audit)")
    ap.add_argument("--target", default=None,
                    help="only consider freezes naming this target, "
                         "e.g. pypi:agent-audit-ledger")
    ap.add_argument("--now", default=None, help="ISO 8601 instant (default: now, UTC)")
    args = ap.parse_args(argv)

    path = os.path.join(args.ledger, "predictions.jsonl")
    if not os.path.isfile(path):
        print("no predictions.jsonl at %s" % path, file=sys.stderr)
        return 2

    now = parse_ts(args.now) or datetime.now(timezone.utc)
    rows, err = latest_rows(path)
    if err:
        print(err, file=sys.stderr)
        return 2

    held = active_freezes(rows, args.target, now)
    if not held:
        print("release freeze: none in force%s."
              % (" for %s" % args.target if args.target else ""))
        return 0

    print("release freeze IN FORCE — not publishing.")
    for pid, target, deadline, x in held:
        print("  %s holds %s until %s" % (pid, target, deadline))
        print("      %s" % (x[:300]))
    print()
    print("Publishing now would end the measurement this prediction is making.")
    print("To publish anyway, first append a row settling that prediction —")
    print("including settling it as 測定不能 because you chose to publish.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
