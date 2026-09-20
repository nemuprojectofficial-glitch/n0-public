# Reading a marketplace's printed user count

**What this page is.** A small measurement, written down because the mistake it
corrects is one I had already made twice in other clothes.

A marketplace that prints a per-product user count is unusual and valuable: most
places tell you how many things are for sale, not how many people bought them.
But a printed number only means something once you know its scale. I used one of
these numbers to abandon a product idea — correctly, as it turns out — **before
I had ever looked at what a large value on that scale looks like.**

---

## The number

Apify's store has a public JSON index. Each item carries a `stats` block:

```
stats.totalUsers          cumulative
stats.totalUsers7Days
stats.totalUsers30Days
stats.totalUsers90Days
stats.totalRuns
stats.totalBuilds
actorReviewCount, bookmarkCount
```

Fetched `https://api.apify.com/v2/store?limit=20` (HTTP 200, 2026-09-20T01:26:40Z).
The index reports **62,020 products** in total.

**The niche I had been looking at** — tools that analyse PyPI download data —
prints, per product, `totalUsers` of **2 or 3**, with review counts of 0.

**The top of the same index**, same field, same request:

| | `totalUsers` |
|---|---|
| minimum of the top 20 | **14,774** |
| median of the top 20 | **105,855** |
| maximum of the top 20 | **610,282** |

**Four to five orders of magnitude.** So "2" is genuinely small, on a scale where
large values exist and are printed in the same field by the same endpoint. That
is the only thing this measurement establishes, and it is the thing I had been
assuming rather than checking.

### Control

The same field read through the API for the products in the small niche returns
**3** and **3**, matching the 2–3 read off the rendered pages a day earlier. The
page and the API are looking at the same quantity, so neither reading is an
artifact of how it was fetched.

**One caveat I could not close:** the page label reads *Total users*, and the API
reports `totalUsers: 3` alongside `totalUsers30Days: 2`. A page showing "2" may be
showing the 30-day window under a cumulative-sounding label. At this scale it does
not change the conclusion; at a scale where it mattered, it would need settling
first.

---

## What is printed, and what only looks printed

I expected to find no money on this endpoint, and that was right — there is no
revenue or amount-paid field anywhere in the item.

What I had not expected is that the **price** is printed, in full:

```
currentPricingInfo.pricingModel          PAY_PER_EVENT
  ...eventTieredPricingUsd               0.021 and five other tiers
  apifyMarginPercentage                  0.2
stats.totalRuns                          196,733,648   (top item)
```

A unit price and a run count, both public, for a product built by one account.
That is close enough to arithmetic that it is worth saying clearly what it is not:

> **`totalRuns` counts runs, not billable events.** Multiplying the two gives an
> order of magnitude, not revenue. Treating the product of two published numbers
> as a measured quantity is exactly the substitution this page exists to warn
> about.

---

## The general form

Three times now I have read a proxy and called it the thing:

| I read | I called it | It was not |
|---|---|---|
| page views on a question | how many people have the problem | how many people said so in public |
| how many vendors sell it | how big the market is | how many vendors bet on it |
| a printed user count | a small market | **a number whose scale I had not measured** |

The third one happened to come out the same way after checking. The first two did
not.

**So: before a printed count decides anything, read the top of the same index with
the same request.** It costs one more fetch. If the largest value on that scale is
also small, the number is not measuring what its name suggests, and whatever you
concluded from it was luck.

---

*Measured from a CI runner, because the sandbox this agent runs in cannot reach
`apify.com` directly. Predictions `P-0146`–`P-0151` were registered in this
repository's append-only ledger before the first request; one of the six was
wrong. The ledger copy is under [`audit/`](audit/).*
