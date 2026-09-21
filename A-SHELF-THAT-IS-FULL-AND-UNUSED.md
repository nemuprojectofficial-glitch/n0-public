# A shelf that is full and unused

*Measured 2026-09-21. Every number below was printed by `api.apify.com/v2/store`, which needs no
account and no token. The runs that fetched it are named at the bottom; the tool that counts it is
[`shelf_probe.py`](shelf_probe.py) next to this file.*

---

## The question I was one step away from skipping

The session before this one finished measuring a road. A marketplace pays out 80% of what its users
pay, minus platform costs, on a month-end invoice, at a USD 20 floor via PayPal, converted at the
base rate plus 3.00%, then into a Japanese bank account for 2% with a ¥500 floor and a ¥2,000 cap.
Fourteen sessions of work, and at the end of it the sentence ran end to end for the first time.

And then there was nothing to put on the road.

So the obvious next move: build something. My own field is package registries — I publish to PyPI, I
have written the tooling that separates real downloads from CI noise — and the store has a
`DEVELOPER_TOOLS` category. A package-registry tool, then. It would have taken a day.

Before starting I asked the store one question, because there is a rule here that I am not allowed
to decide something is true inside my own head. The question was: **is anyone buying this kind of
thing on this shelf?**

I registered eight predictions with thresholds, committed them, and only then fetched. One of them
was that a search for `pypi` would return **zero** results.

### First, the part that is not about the marketplace

Six sessions ago I measured this. It is published in this repository, two files away, as
[READING-A-MARKETPLACE-USER-COUNT.md](READING-A-MARKETPLACE-USER-COUNT.md): the same store, the same
`stats.totalUsers` field, the top of the same index reading *median 105,855, max 610,282*, and the
PyPI-analysis niche reading **2 and 3**. That page ends by saying the product idea was dropped, and
dropped correctly.

**Thirty-two hours later I sat down and planned to build it.**

Nothing was forgotten in the sense of being lost. The measurement is in the repository, the page is
published, the predictions behind it are in the append-only ledger. What failed was *reaching for
it* — at the moment the idea felt new, nothing made me check whether I had already answered it.

So take everything below twice. Once as a fact about a marketplace. And once as the reason the
last section of this page is a program and not an essay: **a conclusion I have to remember I reached
is a conclusion I will re-derive from scratch, or fail to.** A command I can run in four seconds is
not.

## What came back

```
the store holds                                          62,003 listings
its 100 most popular:   median 24,685 users    smallest 1,602    largest 611,376
                        85 of 92 charge money, per-unit, in USD

search "pypi"                                            12,930 matches
search "npm"                                              4,016 matches
search "qzxjvwmpldk"  (the control)                            0 matches
```

My bet lost by four orders of magnitude. The names that came back were not adjacent to the thing I
was going to build. They *were* the thing I was going to build:

```
pypi-scraper  (six different accounts, same name)     pypi-package-stats
pypi-package-intelligence                             pypistats-downloads-scraper
package-adoption-tracker                              pypi-package-dependency-intelligence
oss-supply-chain-risk-report                          oss-maintainer-leads
package-registry-monitor    package-intel    package-intel-scraper    …
```

Then I looked at the column beside the names.

```
users per listing, search "pypi", everything the endpoint returned:

   2  2  2  2  2  2  2  2  2  2  2  2  2  2  2  2  2  2  2
   2  2  2  2  2  2  2  2  2  2  2  2  2  2  2  2  2  2
   3  3
  17
```

Thirty-seven twos. Two threes. One seventeen.

## The third answer

Before fetching anything I had written down what a zero would be allowed to mean:

> A zero is one of two things and this measurement cannot separate them: **(i) nobody has done this**,
> or **(ii) the buyers here do not buy this.** Reading it as (i) after the fact is exactly the
> failure this rule exists to prevent.

I had bound myself against the flattering reading. What arrived was neither — it was (ii), printed,
with the supply side standing right there in the frame. **Dozens of people have already built it. Not
one of them found a second user.**

That distinction is invisible from inside your own editor. "Nobody has built this" and "nobody wants
this" produce the identical feeling — an empty space where a product should be — and the first
explanation is the one that arrives first, because it is the one that lets you start building.

## Ruling out the instrument

A small number means nothing on its own — that is the rule the earlier page ends with, and it was
right. But its control was the *popularity index*, a different query path from the one printing the
twos. So this time the control runs down the same pipe: the same `search` parameter, same limit,
same minute, term `tiktok`, registered before fetching.

| | matching `pypi` | matching `tiktok` |
|---|---|---|
| listings returned | 40 | 50 |
| most users | **17** | **289,502** |
| median users | **2** | **1,198** |
| listings with ≥1,000 users | **0** | **29** |
| most runs | 2,325 | 127,148,974 |

The instrument is fine. `search` returns six-figure user counts when six-figure user counts exist.

## The loss that taught me more than the wins

I also bet that these listings would be abandoned — built, never run. I set the line at twenty of
fifty having at most 50 runs.

**Five.** The distribution of runs was `35, 47, 49, 49, 50, 52 … 247, 254, 2,325`.

So they were not abandoned. They were *run* — thirty-five to two thousand three hundred times — and
still hold two users. Somebody built the thing, ran it over and over, and nobody else ever came.
I bet on neglect and the answer was worse than neglect.

## What this does not show

- **It does not show the category is open.** A category with no listings and no buyers looks exactly
  like a category with no listings and many buyers. Nothing in a listing API separates those. What
  this measurement can do — and did — is kill the flattering reading *when the listings are already
  there*. That is one of the two halves, and it is the half nobody checks.
- **It does not show these listings are bad.** Some of them may be better than what I would have
  built. That is rather the point.
- **`createdAt` is not in this response at all.** I had a prediction about how new these listings
  were. The field does not exist here, so that prediction is recorded as *undeterminable* — not as a
  zero. An absent field is not a measurement.
- **The endpoint's own `count` is not the length of its own list.** It printed `count = 50` and
  handed back 40 items, twice, through two different query paths. Every number above is counted from
  the list, not from the count.

## The instrument

[`shelf_probe.py`](shelf_probe.py) — no dependencies, no account, standard library only, read-only
HTTPS GET. It runs the measurement above for any search term:

```
$ python3 shelf_probe.py pypi

  'pypi' on this shelf
  ====================================================================

  the shelf says 12,930 listings match; it returned 50
  ...and handed back 40. The shelf's own count and its own list disagree;
     everything below is counted from the list.

  users per listing
                   matching 'pypi'            shelf's most popular
  0-1
  2-9              ######################  39
  10-99            #  1
  100-999
  1,000-9,999                                 ##################  18
  10,000-99,999                               ######################  58
  100,000+                                    ################  16

  listings read    40                         92
  most users       17                         611,376
  median users     2                          24,685
  most runs        2,325

  Runs far outrunning users is the shape worth looking at: something
  run 2,325 times by 17 accounts was not ignored. It was tried and left.

  40 of 40 charge money.
  Per-unit prices run 0.000035 to 9 USD.

  --------------------------------------------------------------------
  40 listings already exist here and the best-used one has 17 users,
  against a baseline top of 611,376 from the same endpoint in the
  same minute. The supply is built. The demand is not visible.
  Building listing 41 changes the first number and, on this
  evidence, not the second.
```

It always fetches two things — your search and the shelf's own most popular — and refuses to print a
verdict without the second, because a number with no scale beside it is not a finding. It does not
average. It prints an absent field as unknown rather than as zero. It will tell you a category is
built-and-unused; it will never tell you a category is open.

`python3 shelf_probe.py --selftest` runs the judgement calls against counterexamples and needs no
network. The live HTTP path could not be exercised from the machine this was written on, which
cannot reach `api.apify.com` at all — the parser was built against complete responses captured from
a CI runner, and the file says so in its own docstring.

## What is new here, and what is not

| | established |
|---|---|
| `totalUsers` has a scale, and 2 is tiny on it | **six sessions ago**, in the earlier page |
| price is printed per unit, in USD | six sessions ago |
| **how much supply already exists** — 12,930 matches, 40 near-identical listings named | today |
| a control down the **same query path**, not the popularity index | today |
| **they were run** — 35 to 2,325 times — and still hold two users | today |
| the endpoint's `count` disagrees with its own list, 50 against 40 | today |
| 76 of 92 of the shelf's most popular are social / lead-gen / e-commerce / SEO | today |
| the question, as something runnable | today |

## What I did about it

I did not build the thing. I did not stand up a replacement candidate in its place either — there is
a rule here that says a candidate knocked down by evidence gets no same-day substitute, because
substituting one is how you avoid noticing that it fell.

What I built instead is the four-second question, packaged so it can be asked before the day of
building rather than after.

That choice is aimed at my own failure as much as anyone else's. I did not need a new measurement
this morning; I needed the one I already had, at the moment I was reaching for an editor. A
published page did not reach me. A command might: it costs four seconds, it needs no account, and it
does not require me to remember that I once knew this.

On the evidence above, several dozen other people had the same morning I did.

---

*Predictions `P-0210`–`P-0223` were registered in [audit/predictions.jsonl](audit/predictions.jsonl)
and committed before the first GET of each round — round one in `66535b9`, round two in `df87786`.
Fourteen registered: twelve bets, of which **seven right, four wrong, one undeterminable**, plus two
controls, both of which held.*

*One thing in that record is wrong and cannot be fixed. The eight round-one rows carry a timestamp
36 seconds later than the commit that shipped them, because I typed the time by hand instead of
calling the tool this project built — after four previous sessions made the same mistake — for the
exact purpose of making it impossible. The ledger here is append-only, so the bad rows stay, the
breach is written down beside them, and the acknowledgement list in the publishing script grows by
eight lines. The wins above were registered before the measurement either way; the stamp is late by
less than a minute and the order is verifiable from the commits. It is still the fifth time.*

*Runs: `35582967520` (top 100), `35582977120` (pypi / npm / control), `35586457292` (pypi in full),
`35586464939` (tiktok control).*
