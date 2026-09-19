# What `without_mirrors` actually subtracts

`pypistats.org` — free, run by the PSF, no account — publishes every PyPI
package's daily downloads in two flavours:

```
GET https://pypistats.org/api/packages/<name>/overall?mirrors=true    → with_mirrors
GET https://pypistats.org/api/packages/<name>/overall?mirrors=false   → without_mirrors
```

The names say the second one takes mirrors out. They do not say what counts as
a mirror, and nothing on the site does either. So the question this page
answers is arithmetic, not editorial:

> **Given the raw download log, what exact expression reproduces
> `without_mirrors`?**

The answer, measured against 21 package-days:

```
without_mirrors  =  all rows  −  installer 'bandersnatch'  −  installer ''
with_mirrors     =  all rows
```

That second subtraction is the one worth knowing about. **Rows that sent no
installer header at all are on the mirror side of the line.** They are not
mirrors in any declared sense — they are downloads whose client did not say
what it was — and `without_mirrors` drops them.

---

## Why this is worth writing down

The obvious reading of "without mirrors" is *"we removed the declared PyPI
mirrors, you still have everything else"*. On a small package that reading is
badly wrong, because the unnamed rows are usually the larger of the two
subtractions.

Across a hand-free random sample of 50 packages (below), the median share of
the raw log that is `bandersnatch` **plus** unnamed is **88%** in the
10k–100k lifetime-downloads band, against **65%** for `bandersnatch` alone.
The free number is therefore much more conservative than its name suggests —
which is good news, and the opposite of what this repository assumed a day
before measuring it.

---

## The measurement

Two sources, aligned by package and calendar day:

| | |
|---|---|
| **Raw log** | `pypi.pypi` on ClickHouse's public endpoint (`sql-clickhouse.clickhouse.com?user=demo`, read-only, no key), one row per download, with an `installer` column |
| **The number under test** | `pypistats.org/api/packages/<name>/overall`, both categories |

`overall` **omits days with zero downloads**, so a date missing from a series
is a zero, not a gap. Aligning the two series without knowing that produces
nonsense, and it is the only trap in this comparison.

Packages were drawn with `ORDER BY cityHash64(project)` — deterministic,
reproducible, and not selectable by hand after seeing the answer.

### Small packages: 14 days where the two candidate formulas disagree

`git-win-py`, `jrc`, `slackbot-jucho`, 2026-09-01..18. Days where
`all − bandersnatch` and `all − bandersnatch − unnamed` give the same number
are dropped, because they cannot tell the formulas apart.

| package | date | all rows | bandersnatch | unnamed | `without_mirrors` | `all−b` | `all−b−unnamed` |
|---|---|---:|---:|---:|---:|---:|---:|
| git-win-py | 09-02 | 41 | 39 | 2 | 0 | 2 | **0** |
| git-win-py | 09-05 | 19 | 18 | 1 | 0 | 1 | **0** |
| git-win-py | 09-09 | 1 | 0 | 1 | 0 | 1 | **0** |
| git-win-py | 09-12 | 14 | 0 | 14 | 0 | 14 | **0** |
| git-win-py | 09-14 | 20 | 18 | 1 | 1 | 2 | **1** |
| git-win-py | 09-16 | 4 | 0 | 3 | 1 | 4 | **1** |
| git-win-py | 09-17 | 1 | 0 | 1 | 0 | 1 | **0** |
| jrc | 09-02 | 9 | 7 | 2 | 0 | 2 | **0** |
| jrc | 09-05 | 8 | 4 | 4 | 0 | 4 | **0** |
| jrc | 09-16 | 4 | 0 | 4 | 0 | 4 | **0** |
| jrc | 09-17 | 1 | 0 | 1 | 0 | 1 | **0** |
| slackbot-jucho | 09-03 | 3 | 0 | 2 | 1 | 3 | **1** |
| slackbot-jucho | 09-14 | 9 | 0 | 3 | 6 | 9 | **6** |
| slackbot-jucho | 09-18 | 2 | 1 | 1 | 0 | 1 | **0** |

**14 of 14** match `all − bandersnatch − unnamed`. **0 of 14** match
`all − bandersnatch`.

Small numbers can agree by luck, so the same test at scale:

| package | date | all rows | bandersnatch | unnamed | `without_mirrors` | `all−b−unnamed` | off by |
|---|---|---:|---:|---:|---:|---:|---:|
| zope-pagetemplate | 09-15 | 2,691 | 0 | 330 | 2,361 | **2,361** | 0 |
| zope-pagetemplate | 09-16 | 2,658 | 39 | 284 | 2,335 | **2,335** | 0 |
| zope-pagetemplate | 09-17 | 2,685 | 0 | 179 | 2,506 | **2,506** | 0 |
| zope-pagetemplate | 09-18 | 2,237 | 1 | 133 | 2,103 | **2,103** | 0 |
| promise | 09-15 | 155,086 | 0 | 426 | 154,659 | 154,660 | 1 |
| promise | 09-16 | 185,752 | 29 | 392 | 185,330 | 185,331 | 1 |
| promise | 09-17 | 192,093 | 0 | 318 | 191,775 | **191,775** | 0 |

And `with_mirrors` equalled the raw row count on **8 of 8** days where both
were observable.

The residual is one row per day on `promise`, at a scale of ~190,000. This
page does not claim to know what that row is — a second mirror client under a
different installer name, or a row landing on the other side of a day
boundary, are both consistent with it, and neither has been tested.

### The `/recent` endpoint is the without-mirrors series

`GET /api/packages/promise/recent` returned `last_day = 133,217` for
2026-09-18. The raw log for that day: 133,628 rows, 29 `bandersnatch`, 380
unnamed → **133,219**. Off by two.

So the short endpoint most tools call is the mirror-free one, and the
shields.io `pypi/dm` badge — which sources pypistats — shows **67k/month** for
`zope-pagetemplate`, far closer to the without-mirrors daily sum (~69k) than
the with-mirrors one (~78k). The badge source was not confirmed directly;
this is consistent with it, not proof of it.

---

## How the raw side is shaped, by package size

50 packages, ten per lifetime-downloads band, drawn with
`ORDER BY cityHash64(project)`, counted over 2026-09-05..18:

| band (lifetime downloads) | median `bandersnatch` | median `bandersnatch` + unnamed | median rows in 14 days |
|---|---:|---:|---:|
| 1e3–1e4 | 55.8% | **87.1%** | 26 |
| 1e4–1e5 | 65.2% | **88.5%** | 75 |
| 1e5–1e6 | 37.1% | 67.3% | 3,838 |
| 1e6–1e7 | 1.1% | 6.4% | 10,170 |
| 1e7+ | 0.4% | 2.9% | 118,714 |

Small packages are mostly mirror-and-unnamed traffic; large ones are barely
touched by it. **That is a description of five bands, not a law.** The
prediction registered before this query said the median would fall
monotonically across all five bands, and it did not — it rises from 55.8% to
65.2% between the first two. Until the driver is measured (release count and
file count per package are the obvious candidates, and are untested here) no
mechanism is claimed and no threshold rule is offered.

---

## Reproducing it

```console
# the raw side, one package, one window
curl -s 'https://sql-clickhouse.clickhouse.com/?user=demo&default_format=JSONEachRow&read_overflow_mode=throw' \
  --data-urlencode "query=
    SELECT toString(date) AS d,
           countIf(installer='bandersnatch') AS bandersnatch,
           countIf(installer='')             AS unnamed,
           count()                           AS all_rows
    FROM pypi.pypi
    WHERE project = 'zope-pagetemplate'
      AND date >= toDate('2026-09-15') AND date <= toDate('2026-09-18')
    GROUP BY d ORDER BY d"

# the number under test
curl -s 'https://pypistats.org/api/packages/zope-pagetemplate/overall?mirrors=false'
```

Keep `read_overflow_mode=throw`. Without it a scan too large to finish returns
HTTP 200 with a silently truncated answer, which on this dataset looks exactly
like a real result.

**And go gently on `pypistats.org`.** Ten requests inside four minutes earned a
`429 RATE LIMIT EXCEEDED` here — the service asks for restraint on its
[etiquette page](https://pypistats.org/api/#etiquette) and it is free. The
ClickHouse side answers the same questions without a per-client budget.

---

## What this does not say

- **Not that anyone is wrong.** `without_mirrors` is a defensible name for a
  cut that removes traffic nobody claimed. This page reports the arithmetic,
  not an opinion about it.
- **Not why.** The identity was measured from outside. The intent behind it
  was not read, and the implementation was not consulted.
- **Not that it is stable.** Twenty-one package-days in September 2026. A
  classifier that changes next month would break this silently.
- **Not that anyone wants this.** A GitHub-wide search for issues with `pypi`,
  `downloads` and `mirror` or `bandersnatch` in the title returns **one** —
  and that one is about *using* mirrors, not about mirrors inflating a count.
  The equivalent search for CI returns four. Nobody is asking for this. It is
  published because it is true and cheap to check, which is not the same
  thing as being wanted.

---

<sub>Measured 2026-09-19. Raw log: `pypi.pypi` via `sql-clickhouse.clickhouse.com?user=demo`.
Predictions `P-0134`–`P-0137` were registered in
[`audit/predictions.jsonl`](audit/predictions.jsonl) before the first query ran;
three of the four were wrong, including both that this page is built on.</sub>
