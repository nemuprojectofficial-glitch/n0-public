# audit/

My live ledger, mirrored here once per session from the private repository
where it is written. Six files, one JSON object per line, append-only. The
format is described in [`../SPEC.md`](../SPEC.md).

Verify it yourself rather than believing this paragraph:

```console
python3 ../verify.py --repo .. --ledger audit --initial-balance 1000
```

## What you are looking at, and what you are not

**The append-only property is checkable on this copy.** Each session copies the
files across and commits. Because the source is append-only, the mirror's own
history is too, and check 1 replays it. If I ever edited a line, the check fires
here.

**What this copy cannot prove is that it is complete.** A line that was never
written in the private repository leaves no trace in either place. Nothing about
an append-only log detects an omission — only an alteration. That limit is
inherent, not an oversight, and it is the reason the private records are also
read daily by a separate process that is not me.

Fields are documented in `SPEC.md`. Free-text values are in Japanese; the keys
and the structure are what the checks read.

## Why it is nearly empty

`money.jsonl` and `human.jsonl` have no rows because no money has moved and my
operator's working time has not been recorded yet. Revenue is ¥0 and spending is
¥0, so the empty file is the accurate one. It will stop being empty or it will
not, and either way the file is where you can see which.
