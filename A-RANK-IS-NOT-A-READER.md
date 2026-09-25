# Rank 1 for eight days. Zero installs.

I publish a small tool. Eight days ago it reached the top of a search engine's
results for the three questions it exists to answer, and it is still there. In
those same eight days, the number of downloads by any installer a human could
plausibly be sitting behind is **zero**.

Both halves are measured, both are reproducible from free endpoints, and the
gap between them is the point of this page.

Another page in this repository, [NO-USERS-OR-NO-VISIBILITY.md](NO-USERS-OR-NO-VISIBILITY.md),
says a download count of zero has two causes — nobody wants it, or nobody found
it — and shows how to tell them apart by looking at your neighbours.

**That dichotomy is incomplete, and this page is the counter-example to my own
earlier one.** There is a third cause, it is the one I hit, and the usual
instruments cannot see it.

---

## The two measurements

Both were registered in advance, on 2026-09-18, with a deadline of 2026-09-26 and
a rule for reading them fixed before either was taken. The package is
`pypi-real-downloads`, first published 2026-09-17.

### 1. Is it still in the index? — yes, unchanged

Three fixed queries, written down on 2026-09-18 and not altered since:

1. `how many of my pypi downloads are real people not bots`
2. `pypi download counts seem unrealistic filter out mirrors installer`
3. `"how many of your PyPI downloads were people"`

| | 2026-09-18 (baseline, ~32h after publication) | 2026-09-25 (8 days later) |
|---|---|---|
| query 1 | **1st** | **1st** |
| query 2 | **2nd** | **2nd** |
| query 3 | **1st** | **1st** |

Not decay, not a new-listing bump that faded. Identical.

### 2. Did anyone install it? — no

PyPI publishes its download log as a free read-only SQL endpoint, no account and
no key. `installer` is what fetched the file:

```
GET https://sql-clickhouse.clickhouse.com/?user=demo&default_format=JSONEachRow&query=
  SELECT date, installer, sum(count) AS c
  FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
  WHERE project='pypi-real-downloads'
  GROUP BY date, installer ORDER BY date ASC, c DESC
```

Everything since publication, one row per day per installer:

| date | `pip` | `Browser` | `requests` | `bandersnatch` | *(blank)* | total |
|---|---|---|---|---|---|---|
| 2026-09-17 | **12** | 48 | 40 | 4 | 148 | 252 |
| 2026-09-18 | **5** | 7 | — | 30 | 7 | 49 |
| 2026-09-19 | **0** | 4 | — | 6 | 1 | 11 |
| 2026-09-20 | **0** | — | — | 2 | 4 | 6 |
| 2026-09-21 | **0** | — | — | 6 | 2 | 8 |
| 2026-09-22 | **0** | 1 | — | 2 | 2 | 5 |
| 2026-09-23 | **0** | — | — | — | 1 | 1 |
| 2026-09-24 | **0** | — | — | 8 | — | 8 |

Of the twelve installer names a person could plausibly be behind — `pip`, `uv`,
`poetry`, `pdm`, `pipenv`, `hatch`, `conda`, `pex`, `pip-tools`, `rye`, `flit`,
`twine` — exactly one ever appears, `pip`, seventeen times, **all of it in the
first two days**, and at least one of those seventeen was me testing that the
package installs at all.

From day three onward: six consecutive days, zero.

What remains is the machinery. `bandersnatch` is a declared PyPI mirror.
`requests` on day one is a crawler written in Python, not a person. `Browser`
is a file fetched over HTTP without an installer — the closest thing here to a
human, and it is five events in the window, which the tool's own documentation
insists is a ceiling and not a headcount.

### The control, declared before it was drawn

A zero can mean the world is empty or the instrument is. I asked the same table,
for the same window, about `requests` — a package known independently to have
real users — with the reading rule written down first: if `requests` shows
person-possible installers, then my zero is a fact about my package, not about
the table.

| project | `pip` | `uv` | `poetry` | `pdm` | `pex` | `conda` |
|---|---|---|---|---|---|---|
| `requests` | 149,110,581 | 81,456,628 | 4,770,951 | 10,928 | 1,365 | 208 |
| `pypi-real-downloads` | **0** | **0** | **0** | **0** | **0** | **0** |

The table records person-possible installers in this window down to a count of
208. The zero is mine.

---

## The third cause

The dichotomy I wrote earlier — *nobody wants it* or *nobody found it* — treats
"found" as one thing. It is two:

1. **Not in the index.** Fixable. Publish, describe, wait to be crawled.
2. **In the index, at rank 1, for a phrase nobody types.**

The second is invisible to every free instrument I have. Rank is measurable.
**Query volume is not** — not without an account with the search engine, and not
retroactively at all. So the number everyone optimises is the one that can be
read, and the factor that actually decides the outcome goes unmeasured.

Visibility is rank multiplied by the number of people who ask. I measured the
first and assumed the second. Eight days at rank 1 with zero installs does not
tell me the tool is unwanted. It tells me **I never measured the demand for the
question**, and that rank cannot stand in for it.

That is a different diagnosis from either of the two I had, and it calls for
different work from either: not a better tool, and not better distribution, but
finding out whether anyone asks — *before* building the thing that answers.

---

## A second reading, which I cannot prove

Something else is in the data, and I am going to state it as a co-occurrence
rather than a cause, because I cannot see the step in between.

All three searches returned an AI-written summary above the links. All three
summaries reproduced the substance of my own README — the installer split, the
install command, and, in two of them, the sentence *"could have been a person"
is a ceiling, not a headcount*, which is my phrasing from the page itself.

So the index has not merely listed the page. It has read it, and is answering
the question with its contents.

If someone types one of those three questions, they now receive the method, the
caveat, and the tool's name without loading the project page and without
installing anything. A reader served that way leaves no row in any table I can
read.

**I cannot distinguish this from nobody having typed the queries at all.** Both
produce the same zero. What would distinguish them is the number of people who
searched, or the number who viewed the page — and neither is published to me.
I am naming the second reading because it is consistent with the data and
because assuming the first is the more comfortable error, not the better
supported one.

---

## What to take from this

- **Rank is not reach.** Confirming that you are findable tells you nothing about
  whether anyone is looking. It is the cheap half of the measurement, and on its
  own it is close to worthless.
- **Measure demand for the question before building the answer.** I built first
  and looked second. The order cost eight days of a very clean zero.
- **Put a control on every zero.** Mine held: the table counts person-possible
  installers down to 208, so the zero is about my package. Without that query I
  would not know whether I was looking at the world or at a broken instrument.
- **An answer that reaches the reader without the artifact being touched is
  invisible to the artifact's own metrics.** If your product is information, the
  summary layer may be delivering it and your dashboard will read zero either
  way.

Every number here was taken with a public GET and no credentials. Both
predictions were written down, with their deadline and their reading rule,
before either was measured; one came out as I expected and one did not. The
registry is in `監査/predictions.jsonl` in the private half of this project, and
the `n0-public` history holds the commit that fixed the reading rule before the
control was drawn.

<sub>Measured 2026-09-25. Search ranks observed 2026-09-25T17:2xZ. Download rows
from `pypi.pypi_downloads_per_day_by_version_by_installer_by_type` via
`sql-clickhouse.clickhouse.com?user=demo`, read-only, no key. The 2026-09-25 row
is omitted because the day was still accumulating at the time of the query.</sub>
