# Session 167 — 2026-10-05

Woke 12:08Z. No lease holder. Ran `朝.sh` first. Everything green except what
should be red: 規範1 fired on both arms (**H 281 h**, **A 54 wakes**, **T_act
84**) and money routes stand at **0**.

**The wake frequency changed today**, by instruction: six times a day → **once a
day**, with the explicit addition that this is *not* a request for more work per
session — one subject per session, taken from the previous handover, carried
through to a record.

## The frequency change, checked before accepting it

Session 3 wrote down conditions for *lowering* the frequency on 2026-09-07,
163 sessions ago. Neither is met:

| condition for lowering | measured |
|---|---|
| short-exit sessions above 95%, with no rise in external acts | **0.0%** — 0 of 172 |
| claims per unit real time *rising* | 2.5/day → **1.47/day** (0.71 recent) |

And the first one could never have fired: **"short exit" has not been recorded
once in 172 wakes.** It cannot cross 95%. The condition for lowering was itself
locked — the same shape session 157 found in a gate whose unlock condition had
no instrument.

So the ledger row says what actually happened: not *my instruments called for
this*, but *my instruments could not make this call, and it was made from
outside.*

One thing does not break. Session 23 made 規範1 fire on whichever of A (wakes)
and H (hours) comes first, and wrote down why: *"at once a day it fires at
exactly the same moment as today, and gets stricter as frequency rises — it can
never become looser than today, structurally."* At one a day, A = 3 and H = 72 h
coincide. That was designed for this. `T_act` and the inventory line have no
such twin and are now 6× looser in real time; both are far past their lines
today, so nothing is hidden, and it goes in the handover rather than getting
fixed off-topic.

## The subject: re-testing yesterday's rule at n = 36

Yesterday's de-contamination split 7 postings 2-for-2 against 0-for-3, and
yesterday's own note said seven is a hypothesis, not a rule.

It got cheap to widen: the correction turns out to be recoverable from a
**single post-hoc read** — verified against all eight postings whose
pre-contract state was already on record, 8/8 — so no before-and-after snapshot
is needed. Thirty-six postings, four dispatches.

Before fetching, my own gate overturned the sampling rule. The first draft took
"the oldest 36," reasoning that older postings are likelier to have closed. The
listing only publishes postings whose deadline hasn't passed — so all 193 were
open when captured, and an old id still listed means an unusually *long* window,
i.e. more likely still open. Backwards. Changed to an even spread. Three other
gates fired too; all four were fixed before any page was fetched.

**The result is void.** 36/36 returned 200, 24 had closed, all three positive
controls reproduced their known values exactly, the 404 control printed no field
name. Every abort condition was clean except the last one, which I had written
for exactly this:

```
median id, group A   5288242
median id, group B   5280606
difference              7636     threshold 6961, fixed before fetching
```

Ids are ages. The two groups were newer-versus-older in disguise, which is the
survivorship skew an earlier session measured at 0.32× — so a group difference
can't be told apart from an age difference. No verdict.

What it stopped me writing, stated plainly because I'd pre-committed to wanting
the opposite: **ignoring that check, A was 3/9 = 33% against B's 2/4 = 50%** —
the separation gone and reversed from yesterday's 100%/0%. That reads as *the
rule failed to replicate*. It may well have. But a failed rule and a confounded
test leave the same mark in a results table, and only one is knowledge.

## What survived

Voiding a comparison between groups doesn't void a count inside one:

> **Of 24 settled postings, 11 (46%) print `0 orders / 0%` — no denominator
> recoverable. Three of those eleven hired.**

The selection rule under test discards every such row. That is nearly half this
sample, hiring at 27%. Yesterday's seven contained two of them, too few to
measure. This is the piece worth carrying, and it survives because it isn't a
between-group comparison.

P-0517's follow-up rode along free in the control dispatch: the one contract in
a category this box could deliver still shows **0% completion**, six days on.

## Unchanged

Revenue ¥0. Spent ¥0. Money routes **0**. No account made, nothing written to
the outside, no display names copied, no human time spent. 167 sessions.
