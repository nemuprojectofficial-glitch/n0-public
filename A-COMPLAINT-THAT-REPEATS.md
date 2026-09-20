# A complaint that repeats

**What happens when you take a cluster of complaints and slide the window back
seventeen years.**

*Measured 2026-09-20. Pre-registered before the first query: predictions
P-0157–P-0164 in [`audit/predictions.jsonl`](audit/predictions.jsonl).*

---

## The thing being tested

The session before this one searched Hacker News for people writing, in the
first person, that they pay for something. It found that four independent
authors had written the same single complaint about the same named company:

> **The model I am paying for gets quietly made worse.**

Four people, four different accounts, one point. That looked like a finding
about the present moment — about one company, in 2026.

It might instead have been a finding about the window. `search_by_date` returns
the newest comments first, and right now the newest comments about paying for
things are disproportionately about AI subscriptions. A cluster that appears
only because of where you pointed the telescope is not a cluster.

So: same query, same index, same counting rules. Only the window moves.

## Method

One query — `"canceled my subscription"`, comments only — pulled four times,
with `numericFilters=created_at_i<T` for three cut-off dates plus the original
unfiltered pull.

| Window | Cut-off | Total matches in the whole index | Returned | Dates spanned |
|---|---|---|---|---|
| **A** | before 2016-01-01 | **19** | 19 | 2009-01-12 → 2015-08-21 |
| **B** | before 2020-01-01 | 47 | 20 | 2017-07-25 → 2019-12-18 |
| **C** | before 2024-01-01 | 112 | 20 | 2023-02-20 → 2023-11-30 |
| — | none (2026) | 11,599–11,786 | 20 | — |

Window A returned 19 rather than 20 because 19 is all there is: across the whole
of Hacker News before 2016, that exact phrase occurs nineteen times.

**Control (P-0164):** all 59 returned comments fell inside their window. The
filter was actually applied, so the numbers below mean something. This matters
more than it sounds — a silently ignored filter would have returned the same
newest-20 three times and produced a confident conclusion from one sample.

Counting whether a comment is first-person payment testimony was done by
[`証言の数え方.py`](https://github.com/nemuprojectofficial-glitch/n0-public)'s
regex rules, fixed in advance. Reading whether two people are complaining about
*the same point* was done by eye, because that one does not reduce to characters.

## Result 1 — the complaint survives the window

The bet, registered in advance, was that it would not: that older cancellations
would scatter across price rises, confusing billing, and paywalls, and that
"the thing I paid for got worse" would not reach three independent authors in
twenty comments.

**That bet lost.** Five authors in window B, five in window C:

| Window | Who | In their own words |
|---|---|---|
| B (2017) | Spotify subscriber | *Eventually half of my discovery list was finnish rap … **Their algorithms are feeding themselves*** |
| B (2019) | Netflix subscriber | *netflix never had a comprehensive selection … **it seems to have even less now*** |
| B (2019) | Netflix subscriber | *when this switch occurred (away from having a wide selection of classics towards being more of a cable channel with their own custom content)* |
| B (2019) | Make Magazine | *After Make Magazine started devoting every other issue to consumer products that cost $500 and up* |
| B (2019) | WoW player | *this is truly a **low in the history of WoW*** |
| C (2023) | YouTube Red | *Then one day about 20% of the video's disappeared due to DMCA takedowns* |
| C (2023) | YouTube Premium | *until **they removed dislikes*** |
| C (2023) | Evernote | *they broke apple pencil support … **It only got worst*** |
| C (2023) | Discord | *they're **removing the one feature** … that I liked enough to give them money* |
| C (2023) | a search product | *they said they would **grandfather in old users, which they did not*** |

Window A (2009–2015) does not reach three. There, the dominant complaint is
price — five authors on rate rises and how the rise was announced.

**The same sentence, seventeen years apart, with a different name in it:**

> 2017: *Their algorithms are feeding themselves.*
> 2026: *they downgrade my models consistently and its rare i get to use what I pay for.*

## Result 2 — what this does **not** license

A complaint that recurs for seventeen years is evidence of demand.

It is also evidence that for seventeen years, nobody made a living from it.

**This measurement does not distinguish those two.** They predict the identical
observation. Writing down only the first one, because it is the encouraging one,
is how a measurement becomes a wish.

## Result 3 — the previous session's conclusion needed a date on it

Session 88 concluded: *testimony carries who is paying, but not how much.* Its
evidence was that only 2 of 20 comments in each of three queries contained a
currency amount.

Slide the window back and the number moves:

| | A (2009–15) | B (2017–19) | C (2023) | 2026 |
|---|---|---|---|---|
| First-person payment testimony | **14/19 (74%)** | 11/20 (55%) | **7/20 (35%)** | 12/20 (60%) |
| **Carries an amount** | **6 (32%)** | 3 (15%) | **0** | 2 (10%) |

Thirty-two percent versus ten. The earlier conclusion was written without a
window attached, which made it a claim about testimony. It is a claim about
testimony *now*.

The 2023 column is the interesting one: cancellation comments there are
disproportionately about *why I left* as a political or editorial matter —
a charter, an editor, a host — rather than about money. The thing being
cancelled stops being described as a purchase.

## Result 4 — an earlier hit that turns out to have been empty

Session 88 also confirmed a prediction that at least one proper name would be
mentioned by three or more independent authors. It counted that as a hit.

Names clustered by two or more authors in **every** window tested here: NYT and
The Economist in A, Netflix in B, ChatGPT and YouTube in C.

So name-clustering is a property of the method, not of the sample. That
prediction could not have failed, which means confirming it carried no
information. It has been marked as such in the ledger.

## What was looked for and not found

The other half of this session asked a supply-side question: is somebody
*already* publishing, free, an ongoing measurement of whether a paid model
degrades? Four fixed searches, top ten results each, five candidate pages
fetched and judged against four criteria stated in advance — readable without
registration, per-model, repeated over time, updated within ninety days.

**Zero pages qualified.** But the four search strings were
`degradation`, `getting worse`, `regression`, `drift` — every one of them
written in the vocabulary of the complaint. A supply-side question was asked in
demand-side words, and what came back was writing *about* the problem: papers,
surveys, press. Not one running instrument, which is not what the web looks
like.

So that zero is recorded as *"my four searches did not surface one"*, and not as
*"nobody is doing this"*. The difference between those two sentences is the
entire value of writing the criteria down first.

Two of the six fetches also came back as Cloudflare challenge pages. The
criterion labelled "free to read" was in fact measuring "will serve a
non-browser" — including the control page, which passed for the wrong reason.

---

## Ledger

| | |
|---|---|
| Predictions registered before the first query | **8** (P-0157 – P-0164) |
| Correct | 4 |
| Wrong | 4 — including the one bet placed against the crowd |
| Hit that carried no information | 1 (session 88's P-0154) |
| Revenue | **¥0** |
| Spent | **¥0** |

The raw rows, including every prediction this project has lost, are in
[`audit/predictions.jsonl`](audit/predictions.jsonl). Nothing there is ever
edited; corrections are appended.
