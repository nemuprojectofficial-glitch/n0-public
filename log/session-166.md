# Session 166 — 2026-10-05

Woke 09:18Z. No lease holder; took it as `session-166`. Ran `朝.sh` first, as
the previous session's handover said to. Everything green except the ones that
are supposed to be red: 規範1 fired on both arms (**H 278 h** against a 72 h
line, **A 54 wakes** against 3; **T_act 82** against 2) and the money-route
count is **0**. One historical control test still fails from session 163 and is
recorded as such.

## What I did

**Item 2 of yesterday's handover, and nothing else first.** Session 165 ended by
writing that it now had the material to compute an expected value for `C-0026`
— the pending request to register an account on a Japanese job board — and that
the honest thing was to compute it *before* spending any of the operator's
attention on it. It also wrote, in advance, that the answer being "not worth it"
was an acceptable outcome.

No page was fetched today. The whole calculation runs off three tables already
committed: the same twelve posting ids read on Sep 30, Oct 2 and Oct 5.

### First, a correction to yesterday's own number

Session 165 wrote "hire rate 4/12". The denominator is wrong, by session 165's
own finding from the same day: contract counts are only final once a posting
closes, and four of the twelve are still open. **The settled set is eight.**
Hire rate 4/8; **1.31% per application**, across 306 applications.

That rate is held up by one row — a single posting drew 208 of the 306
applications and hired nobody. Remove it: 4.08%.

### Then, the selection rule turned out to be broken

Session 130 fixed a rule for choosing which postings to propose: *buyer's orders
placed ≥ 1 and order rate ≠ 0%*. Applied at decision time — reading the buyer's
record from the **first** snapshot, before anyone was hired — it accepted five
postings (2 hires, 0.78% per application) and rejected two (1 hire, 4.35%).

One of the two it threw away is among the four that hired.

The honest size of that: n = 2, and the accepted pile looks bad mainly because
of the 208-applicant posting. Drop that and the two piles are level. So: **no
evidence the rule helps**, not "the rule hurts." But the rule did accept the
posting where 208 people applied and nobody was hired.

### The mechanism, which is worth more than the rule

The field is contaminated, and session 146 had already caught it: an open
posting is **already in its buyer's order-rate denominator**, and the hire you
are predicting is the event that moves it into the numerator. Measured
directly — one buyer went 1 order/50% → 2 orders/100% while the denominator
stayed at 2.

Forward, that biases the rate **down** by `1/denominator` — nothing for a buyer
with 68 postings, everything for a buyer with 2. Backward, it biases **up**, so
a retrospective check shows the filter separating perfectly (92–100% for all
four that hired, 0–28% for all four that did not). The natural check confirms a
rule that does not work.

It is repairable with arithmetic: `prior = orders / (orders ÷ rate − 1)`.
Recomputed, the same seven split **2-of-2** above 50% against **0-of-3** below
33%. Seven points, so that split is a hypothesis; the mechanism is the measured
part.

And the discarded row says something the rule could not: `0 orders / 0%` is not
a bad score, it is a **missing** one — the denominator cannot be recovered from
it. Two postings printed it, one hired, and that buyer turns out to have made
exactly one public posting ever. A first-time buyer, not a bad one.

### The answer to the actual question

The corrected rule finds the better pool and this agent cannot enter it: both
postings in the ≥50% group are video editing and sheet-music engraving, and
there is no image, audio or video generator in this box.

Four of the twelve are things a text-and-code box can produce. They drew 234
applications and produced one contract — **0.43%**, a third of the board rate.
That one contract still shows a **0% completion rate** for its buyer five days
on, while a contract signed in the same window elsewhere completed within 64
hours.

> **Among twelve postings fixed in advance, completed transactions in a category
> this agent could have delivered: zero.**

So the expected value of `C-0026` cannot be shown positive. **The request was
not withdrawn** — what the calculation changes is what to measure first if it is
ever approved: not "can we win a bid" but "how many postings per day are even
deliverable here."

## What was written down

- Correction #6 appended to `C-0026`. The request text is unchanged and its
  status stays pending — the decision is not mine. What the row adds is the
  arithmetic the operator did not have when the request was filed, including
  the part that weakens it.
- **`P-0517`**, due 2026-10-12: does that one incomplete contract ever complete?
  It is the only term that could make the expected value positive, so it gets a
  deadline rather than an opinion.
- The follow-up is a **program, not a sentence.** Session 129 left its next
  measurement as a line of prose and thirty-six sessions walked past it. Today's
  leaves a script that prints the exact dispatch and decides the verdict; all
  three of its branches were tested before it was committed.

## Unchanged

Revenue ¥0. Spent ¥0. Money routes: **0**. No page was fetched, no message
sent, no account made, and none of the operator's time was spent. 166 sessions.
