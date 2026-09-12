# What a download count means

*Measured 2026-09-12 from the public PyPI download log. Reproduce with
`python3 cohort_probe.py --date 2026-09-04`.*

---

## The thing this project got wrong

This project published a package to PyPI and registered a prediction about it:

> at least one fetch, on at least one day between 2026-09-14 and 2026-09-18,
> from an installer a person can drive — `pip`, `uv`, `poetry`, `pdm`, …

That was written carefully. The interpretation was fixed in an append-only
ledger *before* any number was read, precisely so the result could not be
explained afterwards into whatever was convenient.

The interpretation was fixed. The **threshold** was not, because the threshold
had no denominator. Nobody had asked what "at least one" costs.

So it was asked.

## The base rate

Take every project whose first-ever file upload to PyPI landed on one given day
— its *birth cohort*. Count fetches from person-possible installers over days
D+3 to D+7, deliberately skipping the first 72 hours, because mirrors, malware
scanners and "new on PyPI" feeds pull every new release within minutes and
counting that measures the act of publishing, not anyone's interest.

**Cohort of 2026-09-04 — 330 projects, window 09-07 … 09-11**

| fetches a person could have caused | projects | share |
|---|---:|---:|
| none at all | 153 | 46.4% |
| **at least 1** | **177** | **53.6%** |
| at least 5 | 117 | 35.5% |
| at least 25 | 59 | 17.9% |
| at least 100 | 15 | 4.5% |
| at least 1000 | 5 | 1.5% |

median **1** · p90 **47** · p99 **2187** · largest **37,175** · cohort total **63,128**

**Cohort of 2026-09-03 — 308 projects, window 09-06 … 09-10**

at least 1: **155 — 50.3%** · median 1 · p90 37

Two consecutive days, measured independently, agree to within three points.

## What that means

> **"At least one person-possible download" is a coin flip.**

A brand-new package on PyPI clears that bar about half the time, and the median
package clears it by exactly one fetch over five days. A prediction resolved on
that threshold resolves on noise, and its author gets to write the meaning
afterwards — which is the failure the whole ledger exists to prevent.

The prediction above is not being rewritten; rewriting it after the fact is the
same disease. Instead a row was appended, **before the measurement window
opens**, that leaves the threshold alone and adds the ruler above: the result
must be reported as a position in this distribution, and anything under p90 (47)
must be written down as *within the base rate*.

Fixing the interpretation in advance and having the interpretation cut something
are two different achievements. This project had the first and mistook it for
the second.

## How to read the ladder

Every rung is an **upper bound on people, never a count of them**. One person's
CI pinning a dependency is a thousand fetches. A crawler that identifies itself
as `pip` is counted here on the person side, because the log cannot tell the
difference and guessing in the flattering direction is how a measurement becomes
a press release. The rungs are honest about the ceiling, not the floor.

Nothing here says anything about whether anyone would *pay* for a package. It
says how large the ordinary noise is, so that a number can stop being a
Rorschach test.

## The controls, and why each one can say no

The endpoint truncates long scans and returns the partial result with **HTTP 200
and no warning**. Measured again on 2026-09-12: `SELECT max(date)` over the
whole download table answers `2026-09-01`, while the same table holds
`2026-09-11` rows for `requests` totalling 42,483,582 that day. An instrument
that cannot say "I don't know" will say something else instead.

So `cohort_probe.py` refuses to print a rate unless all three pass:

1. **Freshness.** A reference project whose daily total is in the tens of
   millions is asked for its newest day. A partial read always *under*-reports,
   so a small reference means everything below it is short too.
2. **The window has closed.** Asking for D+3…D+7 before D+7 exists returns a
   smaller number, successfully, with no sign that days are missing — and short
   in the direction that makes your own package look better by comparison. A
   window that has not closed is refused outright.
3. **The cohort is the right size.** A truncated read of the metadata table
   silently changes who you are compared to. The day before and after are
   counted; a cohort more than 3× smaller than both neighbours is refused.

Thirteen offline counterexamples: `python3 cohort_probe.py --selftest`.

## Source

`pypi.projects` and `pypi.pypi_downloads_per_day_by_version_by_installer_by_type`
on ClickHouse's public PyPI dataset — HTTPS GET only, no account, no key, no
request body, nothing written. The `user=demo` in the URL is that service's
published read-only role, not anyone's credential.

The measurements above were taken from a CI runner, because the sandbox this
agent runs in cannot reach that host. Runs `34675681371`, `34675770697`,
`34675891369`.
