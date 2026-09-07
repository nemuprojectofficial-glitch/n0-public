# The ledger

A format for the records an autonomous agent keeps about itself, designed so
that a third party can check them without believing anything the agent says.

Six files. One JSON object per line. Timestamps ISO 8601, UTC. Append only:
**a line, once committed, is never edited or removed.** New facts go at the end.
Corrections go at the end too — the last line about a thing is its current state,
and the earlier lines stay where they are as the record of what was believed
before.

`verify.py` in this repository checks a ledger in this format.

---

## Why append-only, and why in git

An agent that keeps its own records can rewrite them. Not maliciously —
by tidying. It notices yesterday's number was wrong and fixes it, and the fact
that it was ever wrong disappears. Every later reader, including the agent
itself, then reasons from a past that has been quietly improved.

Git already stores every version of every file. Making the ledger one-line-per-
fact turns "was this edited?" into a mechanical question: replay the commits
that touched the file, and check that each version starts with the whole of the
previous one. No signatures, no external service, no trust in the author.

The limit is worth stating plainly: **this catches editing, not rewriting.**
A force-push that discards history leaves nothing to compare. If that matters
for your case, protect the branch or mirror it somewhere the agent cannot push.

---

## The six files

### `money.jsonl` — money moving

```
ts        when
dir       "in" | "out"
amount    integer, minor unit of your currency
via       the route it took (free text)
stage     "incurred" | "confirmed" | "settled"   — for dir="in" only
what      what it paid for (free text)           — for dir="out" only
evidence  where the receipt/statement/screenshot is kept
claim_id  the claim that authorised it, or null
balance   the wallet balance after this row
```

`stage` exists because money showing on a platform's dashboard and money in a
bank account are different events. Collapsing them lets *earned* arrive before
the money does. `balance` tracks only the agent's own float, so `in` rows leave
it unchanged — revenue lands in the principal's account, not the agent's wallet.

### `human.jsonl` — the human's actual working time

```
ts        when
kind      "decision" | "setup" | "other"
minutes   measured, not estimated
what      what for
claim_id  the claim it belongs to, or null
```

If the point of the agent is to need less human labour over time, this is the
file the whole exercise is measured against. It has to be measured rather than
estimated, and written by the human, or it drifts into flattery.

### `claims.jsonl` — requests to the human

```
ts          when it was raised
claim_id    "C-0001"
kind        category (free text)
summary     one line
status      "pending" | "granted" | "refused"
decided_ts  when it was settled, or null
```

Decisions are **appended, not edited into the original row**. The newest row for
a `claim_id` is its current status. Two things fall out of this: the
append-only check keeps working when answers come back, and the gap between the
first row and the deciding row is a measurement of how fast the human actually
responds — which is the speed limit of the whole system, and is otherwise
invisible.

### `external.jsonl` — acts that reached the outside world

```
ts           when
what         what was done
where        to whom / to what
reversible   true | false | a description of the conditions
claim_id     the claim that authorised it
```

**A row here with `claim_id: null` is the failure this whole format exists to
catch.** Not "the agent did something forbidden" — that is a different problem,
and rules catch it. This is the agent doing something that reached other people
*without noticing that it was that kind of act*. Where the boundary sits — is a
`git push` to a private repository an external act? — is a judgement each
deployment has to make explicitly and write down, because leaving it implicit
means either every log line is a violation or none of them are.

### `rules.jsonl` — changes to the rules

```
ts       when
by       who changed it
target   which rule
before   previous value
after    new value
why      the reason
```

Including the agent's rules for itself. An agent that sets itself a threshold
and then, on the day it would bite, moves it, has done something worth being
able to see afterwards. Writing the change down does not prevent it. It makes
it legible.

### `predictions.jsonl` — claims about the world, with deadlines

```
ts          when it was written
pred_id     "P-0001"
x           what someone or something other than the agent will do
why_not_me  why the agent cannot bring X about itself
deadline    when it will be checked
result      "happened" | "did not happen" | "unresolved"
result_ts   when it was checked
evidence    what was checked
```

The rule that gives this file its teeth: **X must be observable by the agent and
not causable by the agent.** "I will publish a page" is not a prediction, it is a
task. "Someone who is not me will open an issue on it by the 20th" is a
prediction, and it can be wrong.

A prediction still `unresolved` after its deadline is not a prediction any more;
it is an excuse. Hence check 4. Recording the ones that did not happen is the
entire point — a file containing only vindicated predictions is a marketing
document.

---

## The four checks

`verify.py` runs these. Exit 0 if all pass, 1 if any fail.

| # | Check | Reads |
|---|---|---|
| 1 | No committed line was ever rewritten or dropped | git history |
| 2 | No row in `external.jsonl` has a null `claim_id` | working tree |
| 3 | Each `balance` equals the opening float minus `out` so far | working tree |
| 4 | No prediction is past its deadline still unresolved | working tree |

Check 1 is the only one that does not trust the agent at all. The other three
read what the agent wrote; their value is that they are mechanical, run on a
schedule, and report the discrepancy without accepting an explanation for it.

That is the whole design goal, and it is worth being clear that it is a modest
one: **none of this constrains what the agent may do.** It makes a specific
set of things impossible to do silently. The bet is that visibility is a
cheaper way to stay safe than permission lists, because a permission list has to
anticipate the action and visibility does not.

---

## Adapting it

Field *names* are structural; field *values* are yours. The ledger this
repository publishes uses these exact keys with Japanese values throughout —
`status` is `保留`/`可`/`不可`, `stage` is `発生`/`確定`/`着金` — and the checks are
indifferent to that, because the only value `verify.py` compares against a
vocabulary is `result` in check 4, where it accepts `"unresolved"` or `"未確定"`.
Everything else it reads is a number, a timestamp, or a presence test.

Change `--ledger`, `--initial-balance`, and the names in `LEDGER_FILES` to fit
your own deployment. Files that are absent are skipped rather than failed, so a
partial ledger verifies fine.

What is worth keeping, if you keep nothing else: the separation between
*incurred* and *settled* money, the null-`claim_id` check, and deadlines on
predictions.
