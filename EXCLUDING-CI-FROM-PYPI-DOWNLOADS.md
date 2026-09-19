# Excluding CI from your PyPI download counts

**The download log has a `ci` field. It is free, it is public, and it is not on
the tables most tools read.**

Measured 2026-09-19. Every number and every error message below came back from
the endpoint named here; nothing is illustrative.

---

## The short version

```sql
SELECT date, installer, ci, count() AS count
FROM pypi.pypi
WHERE project = 'your-package'          -- PEP 503 normalized
  AND date >= toDate('2026-08-18')
GROUP BY date, installer, ci
ORDER BY date, count DESC
```

against ClickHouse's free public demo endpoint:

```
https://sql-clickhouse.clickhouse.com/?user=demo&default_format=JSONEachRow&read_overflow_mode=throw&query=...
```

No key, no account, no sign-up. `ci` comes back as `true`, `false` or
`unknown`.

If you would rather not write SQL, `real_downloads.py` in this repository
prints it for one package in two lines — see
[YOUR-DOWNLOADS.md](YOUR-DOWNLOADS.md).

---

## Why most tools do not show you this

PyPI's download log is published in aggregate as a set of per-day summary
tables. Those are the ones everything reads, because they are small and fast:

```
pypi.pypi_downloads_per_day_by_version_by_installer_by_type
pypi.pypi_downloads_per_day_by_version_by_country
...
```

**Every one of them has aggregated `ci` away.** The flag survives only on the
event-level tables:

```
pypi.pypi        ci  Enum8('false' = 0, 'true' = 1, 'unknown' = 2)
pypi.pypi_raw    ci  Nullable(Bool)
```

There is no announcement to have missed and no permission to have been denied.
The column is simply one `DESCRIBE` away from a query plenty of people have
been writing for years.

`pypistats.org`, which is hosted by the PSF and is the free default answer to
this question, states the opposite in its own FAQ:

> **What about downloads due to CI/CD tools?**
> Downloads from CI/CD tools are included in all metrics. There is currently no
> easy way to attribute downloads to build/deployment tools.

That is accurate about the tables `pypistats.org` reads. It is not accurate
about the dataset.

---

## What it actually changes

`pypistats` — the CLI, a package with a real user base — over
2026-09-11 to 2026-09-17:

| | downloads |
|---|---:|
| headline (everything) | 16,976 |
| could have been a person (installer split alone) | **16,548** |
| of those, **declared CI** | **6,008** |
| of those, did not declare CI | 10,540 |

**36% of what an installer-only split calls "person-possible" says, in the log,
that it was a CI runner.** Per day it ranged from 19% to 43%.

The same week, by day:

| date | person-possible | declared CI | remaining |
|---|---:|---:|---:|
| 2026-09-11 | 2,818 | 1,180 | 1,638 |
| 2026-09-12 | 1,463 | 359 | 1,104 |
| 2026-09-13 | 1,391 | 259 | 1,132 |
| 2026-09-14 | 1,956 | 594 | 1,362 |
| 2026-09-15 | 2,589 | 1,016 | 1,573 |
| 2026-09-16 | 2,868 | 1,221 | 1,647 |
| 2026-09-17 | 3,463 | 1,379 | 2,084 |

Note what dominates the person-possible side: **`uv`**, at 71–88% of it. A CLI
tool being fetched three thousand times a day is mostly not three thousand
people, and the installer column alone cannot say so. The `ci` column says so
for about a third of it.

---

## What it does not tell you

**"Did not declare CI" is a lower ceiling, not a headcount.**

- A Docker build, a dependency bot, or a self-hosted runner that sets none of
  the environment variables PyPI's collector looks for lands on the
  *not-CI* side. The flag detects declared CI, not automation.
- `unknown` is a real value and it is not the same as `false`. Fold it into
  either side and you have invented a number.
- It says nothing about *people*. It removes one identifiable category of
  machine from a figure that still contains others.

Chaining it after the installer split is two independent judgements, and they
should stay separate so you can disagree with one of them: the installer split
removes declared mirrors, browsers and bare HTTP clients; the `ci` flag removes
declared CI from what is left.

---

## The cost, and the failure you want

The event-level table is one row per download. A large package over a long
window will exceed the endpoint's read limit:

```
Code: 158. DB::Exception: Limit for rows (controlled by 'max_rows_to_read'
setting) exceeded, max rows: 1.00 billion, current rows: 1.39 billion.
(TOO_MANY_ROWS)
```

That is `requests` over 30 days, measured. **This is the outcome to want**, and
it only happens because of one parameter:

```
read_overflow_mode=throw
```

Without it, this endpoint returns the aggregate of a **partially-read** scan
with **HTTP 200 and no warning**. A truncated read can only lose rows, so the
wrong answer is always smaller — it always points at *"nobody downloaded
this"*, which is the exact conclusion you came to check. Set `throw` and a scan
too big to finish becomes an error instead of a quiet undercount. See
[A-ZERO-THAT-MEANS-UNKNOWN.md](A-ZERO-THAT-MEANS-UNKNOWN.md).

So: the CI split is available for small and medium packages, and refused for
the largest ones over long windows. Shorten the window. If a tool shows you no
CI line at all, find out which of those two happened before reading it as *no
CI traffic*.

---

## Who asked for this, and when

Not a market estimate. These are the public threads, with their dates, read
from the GitHub API on 2026-09-19.

On **2024-08-27**, eight minutes apart, one person filed the same request in
two places:

| | filed | state on 2026-09-19 |
|---|---|---|
| [`psf/pypistats.org#73`](https://github.com/psf/pypistats.org/issues/73) — *Use new PyPI attribute to detect CI downloads* | 15:19:40Z | **open**, 0 comments, 5 reactions |
| [`psincraian/pepy#693`](https://github.com/psincraian/pepy/issues/693) — *…differentiate CI downloads from direct user downloads* | 15:27:07Z | **closed 2024-12-03**, 2 comments |

Both bodies point at the same upstream work — [`pypa/pip#5499`](https://github.com/pypa/pip/issues/5499),
[`pypi/linehaul-cloud-function#9`](https://github.com/pypi/linehaul-cloud-function/issues/9),
and [`ofek/pypinfo#157`](https://github.com/ofek/pypinfo/pull/157), which is
where the same request from [2017](https://github.com/ofek/pypinfo/issues/4)
finally landed.

It is still being asked by people who do not know any of the above exists:

* [`zenml-io/kitaru#985`](https://github.com/zenml-io/kitaru/issues/985)
  (2026-09-04) — *Stop CI from installing kitaru from PyPI (skews download
  stats)*. The fix was to change their own CI, because the measurement could
  not be changed.
* [`cubrid-lab/.github#39`](https://github.com/cubrid-lab/.github/issues/39)
  (2026-09-12, open) — a maintainer preparing a presentation, worried a
  reviewer will say *"isn't that just your CI?"*, planning to reconstruct the
  split by excluding GitHub Actions IP ranges in BigQuery.

That last one is the point of this page. The `ci` field would have answered it
directly, for free, in one query.

The whole thing is small: across all of GitHub, four issues have *pypi*,
*downloads* and *CI* in the title.

---

## On paid services

Hosted services charge for this, and a subscription buys real things a SQL
query does not: years of retained history, a UI, an API with a rate limit
somebody maintains, and not having to think about any of the above. That is a
fair trade and this page is not an argument against it.

What this page says is narrower: **the `ci` field itself is not the thing you
are paying for.** It is public, it is free, and one `DESCRIBE` will show it to
you. Know which of the two you are buying.

---

## Reproducing this

Every figure above came from GET requests to the endpoint named at the top,
issued from a GitHub Actions runner on 2026-09-19 and read back out of the
public job logs of this repository. The queries are in this page verbatim.
The tool is
[`reach_probe.py`](reach_probe.py) (`--selftest` runs a counterexample suite
offline) and [`real_downloads.py`](real_downloads.py).

**This repository published the opposite claim until 2026-09-19.**
`reach_probe.py` has been querying this database since 2026-09-12 and
`YOUR-DOWNLOADS.md` has told its readers since 2026-09-17 that the `pip` figure
could not be split into people and runners. Neither had ever run `DESCRIBE`
against the tables it was reading. The correction is [in that
page](YOUR-DOWNLOADS.md#what-the-number-does-not-mean), not quietly dropped.
