#!/usr/bin/env python3
"""cohort_probe.py — what a download count means, next to everything born the same day.

No dependencies. Python 3.8+. Read-only: HTTPS GET only, no credentials, no
cookies, no request body, nothing written anywhere.

Why this exists
---------------
`reach_probe.py` answers "how many of my package's downloads could have been a
person". It came back with a number. A number with no comparison class is not
an answer — it is a Rorschach test, and the person reading it is the author.

This project published a package and then asked whether anyone had fetched it.
The registered prediction said: *at least one fetch from an installer a person
can drive, on at least one day in the week after release.* That sounded like a
real bar until somebody measured the bar:

    of 330 projects whose first-ever upload to PyPI was 2026-09-04,
    177 of them (53.6%) cleared exactly that bar in days 3-7.
    Of 308 born 2026-09-03, 155 (50.3%) did.

A test that a coin flip passes is not a test. The prediction would have come
back "it happened", and it would have meant nothing, and the meaning would have
been written afterwards by the one thing least able to judge it.

So: before reading your own number, read the distribution your number lives in.

What it measures
----------------
A package's *birth cohort*: every PyPI project whose first file upload landed on
the same calendar day as yours. For that whole cohort, the fetches from
person-possible installers over days D+3..D+7 — deliberately starting at D+3, so
the scan wave that hits every new release in its first hours is behind us.

Then it places one project on that ladder.

It does not say "users". It never says "users". Every rung is an upper bound: one
person's CI can be a thousand fetches, and a slow crawler can be five.

What it reads
-------------
ClickHouse publishes the PyPI download log and the release metadata as a free,
read-only SQL endpoint (no account, no key):

    https://sql-clickhouse.clickhouse.com/?user=demo

    pypi.projects                     name, version, upload_time, ...
    pypi.pypi_downloads_per_day_by_version_by_installer_by_type
                                      project, version, date, installer, type, count

Neither is this project's data and neither can be written to from here. The
`user=demo` in the URL is that service's published read-only role, not anyone's
credential.

The three controls, and why each one can actually say no
--------------------------------------------------------
1. **Freshness.** Borrowed whole from reach_probe: a reference project whose
   daily total is in the tens of millions is asked for its newest day. The
   endpoint truncates long scans and returns the partial result with HTTP 200
   and no warning, and a partial read always under-reports — so a reference that
   comes back small means every number below it is short too.

2. **The window must be closed.** ★ This is the control this project did not
   have, and it is the one shaped like its own past mistakes. Asking for
   D+3..D+7 before D+7 exists returns a smaller number, successfully, with no
   indication that days are missing. Every base rate computed that way is too
   low, and too low in the direction that makes your own package look better.
   So the window's last day is checked against the newest day the data actually
   reaches, and a window that is not yet closed is refused outright.

3. **The cohort must be the right size.** A truncated read of `pypi.projects`
   returns a smaller cohort, which inflates nothing and deflates nothing
   obviously — it just quietly changes who you are being compared to. The day
   before and the day after are counted too, and a cohort more than 3x smaller
   than both of its neighbours is refused.

If any control refuses, no rate is printed. Refusing to answer is the feature.

Usage
-----
    python3 cohort_probe.py agent-audit-ledger
    python3 cohort_probe.py --date 2026-09-04
    python3 cohort_probe.py --selftest

Exit status: 0 measured and every control agreed, 1 a control refused,
2 the project or the day has no data to measure.
"""

import argparse
import datetime
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

try:                                            # same flat package, same endpoint
    from reach_probe import (ENDPOINT, ROLE, TABLE, DAILY, PERSON_POSSIBLE,
                             sql_literal, freshness)
except ImportError:                             # running the file on its own
    ENDPOINT = "https://sql-clickhouse.clickhouse.com/"
    ROLE = "demo"
    TABLE = "pypi.pypi_downloads_per_day_by_version_by_installer_by_type"
    DAILY = "pypi.pypi_downloads_per_day"
    PERSON_POSSIBLE = {"pip", "uv", "poetry", "pdm", "pipenv", "hatch", "conda",
                       "pex", "pip-tools", "rye", "flit", "twine"}

    def sql_literal(s):
        return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"

    freshness = None                            # the control is not optional
    print("cohort_probe: reach_probe.py must sit beside this file; its freshness "
          "control is not optional.", file=sys.stderr)

PROJECTS = "pypi.projects"
UA = "cohort-probe (read-only; github.com/nemuprojectofficial-glitch/n0-public)"

# Days after first upload. The lower edge is not 0 on purpose: every new release
# is fetched within minutes by mirrors, malware scanners and "new on PyPI" feeds,
# and counting that wave measures the act of publishing, not anyone's interest.
WINDOW_FROM, WINDOW_TO = 3, 7

# The rungs. Chosen before any package was placed on them, and left alone since.
RUNGS = (1, 5, 25, 100, 1000)

# A cohort this much smaller than both neighbouring days is a short read, not a
# quiet Tuesday.
COHORT_RATIO = 3.0


def q(sql):
    return "{}?{}".format(ENDPOINT, urllib.parse.urlencode({
        "user": ROLE,
        "default_format": "JSONEachRow",
        "query": " ".join(sql.split()),
    }))


def ask(sql, timeout=60):
    """GET one statement. Returns (rows, error). Never raises for the caller."""
    req = urllib.request.Request(q(sql), method="GET", headers={
        "User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        body, status = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:                                        # noqa: BLE001
        return [], "%s: %s" % (type(e).__name__, e)

    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            return [], "status %d, body was not JSON lines: %s" % (status, line[:200])
    if rows and "exception" in rows[0]:
        return [], rows[0]["exception"][:400]
    if status != 200:
        return [], "status %d" % status
    return rows, None


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _day(s):
    return datetime.date(*(int(p) for p in str(s).split("-")))


def installer_list():
    return ", ".join(sql_literal(i) for i in sorted(PERSON_POSSIBLE))


# --- the pieces ----------------------------------------------------------------

def birth_date(project, fetch=ask):
    """The calendar day of the project's first-ever file upload, or None."""
    rows, err = fetch("SELECT toDate(min(upload_time)) AS d FROM {} WHERE name = {}"
                      .format(PROJECTS, sql_literal(project)))
    if err or not rows:
        return None, err or "no row returned"
    d = rows[0].get("d")
    # ClickHouse returns 1970-01-01 for min() over an empty set, which is a date
    # and therefore looks like an answer. It is not one.
    if not d or str(d).startswith("1970"):
        return None, "no upload on record for %r" % project
    return str(d), None


def cohort_sizes(days, fetch=ask):
    """How many projects were first uploaded on each of these days."""
    lits = ", ".join(sql_literal(d) for d in days)
    rows, err = fetch(
        "SELECT toDate(t0) AS d, count() AS n FROM "
        "(SELECT name, min(upload_time) AS t0 FROM {} GROUP BY name) "
        "WHERE toDate(t0) IN ({}) GROUP BY d ORDER BY d".format(PROJECTS, lits))
    if err:
        return {}, err
    return {str(r.get("d")): _int(r.get("n")) for r in rows}, None


def ladder(day, w0, w1, fetch=ask):
    """The whole cohort born on `day`, counted over the window [w0, w1]."""
    sql = """
    WITH c AS (SELECT name FROM {projects} GROUP BY name
               HAVING toDate(min(upload_time)) = {day}),
         d AS (SELECT project, sum(count) AS person FROM {table}
               WHERE date >= {w0} AND date <= {w1} AND installer IN ({inst})
                 AND project IN (SELECT name FROM c)
               GROUP BY project)
    SELECT count() AS n, {rungs},
           quantileExact(0.5)(person)  AS p50,
           quantileExact(0.9)(person)  AS p90,
           quantileExact(0.99)(person) AS p99,
           max(person) AS pmax, sum(person) AS total
    FROM (SELECT c.name AS name, ifNull(d.person, 0) AS person
          FROM c LEFT JOIN d ON c.name = d.project)
    """.format(projects=PROJECTS, table=TABLE, inst=installer_list(),
               day=sql_literal(day), w0=sql_literal(w0), w1=sql_literal(w1),
               rungs=", ".join("countIf(person >= %d) AS ge%d" % (r, r)
                               for r in RUNGS))
    rows, err = fetch(sql)
    if err or not rows:
        return None, err or "no row returned"
    r = rows[0]
    out = {"n": _int(r.get("n")),
           "rungs": {k: _int(r.get("ge%d" % k)) for k in RUNGS},
           "p50": _int(r.get("p50")), "p90": _int(r.get("p90")),
           "p99": _int(r.get("p99")), "max": _int(r.get("pmax")),
           "total": _int(r.get("total"))}
    if not out["n"]:
        return None, "the cohort for %s is empty" % day
    return out, None


def project_total(project, w0, w1, fetch=ask):
    """One project's person-possible fetches over the window."""
    rows, err = fetch(
        "SELECT sum(count) AS person FROM {} WHERE project = {} "
        "AND date >= {} AND date <= {} AND installer IN ({})"
        .format(TABLE, sql_literal(project), sql_literal(w0), sql_literal(w1),
                installer_list()))
    if err:
        return None, err
    return (_int(rows[0].get("person")) if rows else 0) or 0, None


def place(value, lad):
    """Which rung a value clears, and the share of the cohort that clears it.

    Returns (rung_or_None, cleared, share). `rung` is the highest rung the value
    reaches; None means it did not reach the lowest one.
    """
    n = lad["n"]
    best = None
    for r in RUNGS:
        if value >= r:
            best = r
    if best is None:
        cleared = n - lad["rungs"][RUNGS[0]]
        return None, cleared, cleared / float(n)
    cleared = lad["rungs"][best]
    return best, cleared, cleared / float(n)


# --- the controls --------------------------------------------------------------

def window_closed(w1, newest):
    """A window whose last day has not happened yet returns a short answer with
    no sign that it is short. Every base rate built that way is too low."""
    if not newest:
        return False, "the newest available day is unknown, so the window cannot be checked"
    if _day(w1) > _day(newest):
        return False, ("the window ends {} but the data only reaches {}: {} day(s) "
                       "are missing and would be silently counted as zero"
                       .format(w1, newest, (_day(w1) - _day(newest)).days))
    return True, "the window ends {} and the data reaches {}".format(w1, newest)


def cohort_plausible(day, sizes):
    """A cohort far smaller than both its neighbours is a short read of the
    metadata table, which silently changes who you are compared to."""
    d = _day(day)
    before = sizes.get(str(d - datetime.timedelta(days=1)))
    after = sizes.get(str(d + datetime.timedelta(days=1)))
    here = sizes.get(day)
    if not here:
        return False, "no cohort found for %s" % day
    neigh = [x for x in (before, after) if x]
    if len(neigh) < 2:
        return False, ("only %d of the two neighbouring days answered, so the "
                       "cohort size cannot be sanity-checked" % len(neigh))
    if all(here * COHORT_RATIO < x for x in neigh):
        return False, ("the cohort for {} is {} projects while {} and {} have {} "
                       "and {}: more than {}x smaller than both neighbours, which "
                       "is what a short read looks like"
                       .format(day, here, d - datetime.timedelta(days=1),
                               d + datetime.timedelta(days=1), before, after,
                               COHORT_RATIO))
    return True, ("{} projects, against {} and {} on the neighbouring days"
                  .format(here, before, after))


# --- offline self-test ---------------------------------------------------------

def selftest():
    """Counterexamples, run without a network. Each must fail the way it should;
    a check that only ever passes is not a check."""
    fails = []

    def check(name, ok):
        print("  %-62s %s" % (name, "ok" if ok else "FAILED"))
        if not ok:
            fails.append(name)

    LAD = {"n": 330, "rungs": {1: 177, 5: 117, 25: 59, 100: 15, 1000: 5},
           "p50": 1, "p90": 47, "p99": 2187, "max": 37175, "total": 63128}

    # 1. The bar this project actually set for itself is cleared by half the
    #    cohort. That is the finding the whole file exists for.
    check("'at least one' is cleared by 53.6% of a birth cohort",
          abs(LAD["rungs"][1] / float(LAD["n"]) - 0.536) < 0.001)

    # 2. Zero is a measurement, not missing data, and it must be placed.
    rung, cleared, share = place(0, LAD)
    check("zero is placed at the bottom, not treated as unknown",
          rung is None and cleared == 153 and abs(share - 0.4636) < 0.001)

    # 3. A value exactly on a rung clears it. Off-by-one here would move a
    #    package a whole decile.
    check("a value equal to a rung clears that rung", place(25, LAD)[0] == 25)
    check("one below a rung does not clear it", place(24, LAD)[0] == 5)

    # 4. The window control must refuse a window that has not closed yet. This
    #    is the failure the rest of the file is built around.
    ok, why = window_closed("2026-09-18", "2026-09-11")
    check("a window ending after the last available day is refused",
          ok is False and "7 day(s) are missing" in why)
    check("a closed window passes", window_closed("2026-09-11", "2026-09-11")[0] is True)
    check("an unknown newest day is refused, not assumed fresh",
          window_closed("2026-09-11", None)[0] is False)

    # 5. The cohort-size control must refuse a cohort far under both neighbours,
    #    and must not fire on ordinary day-to-day variation.
    ok, why = cohort_plausible("2026-09-04",
                               {"2026-09-03": 308, "2026-09-04": 12, "2026-09-05": 256})
    check("a cohort far under both neighbours is refused",
          ok is False and "short read" in why)
    check("real day-to-day variation does not fire",
          cohort_plausible("2026-09-04",
                           {"2026-09-03": 308, "2026-09-04": 330,
                            "2026-09-05": 256})[0] is True)
    check("a missing neighbour is refused, not assumed fine",
          cohort_plausible("2026-09-04",
                           {"2026-09-04": 330, "2026-09-05": 256})[0] is False)

    # 6. min() over no rows returns the epoch, which is a date and therefore
    #    looks like an answer.
    def epoch(sql, timeout=60):
        return [{"d": "1970-01-01"}], None
    check("an empty min(upload_time) is not read as a 1970 birthday",
          birth_date("nope", fetch=epoch)[0] is None)

    # 7. An unreadable count is not rounded down to zero.
    def unreadable(sql, timeout=60):
        return [{"person": None}], None
    check("an unreadable project total is 0 only because there is nothing to sum",
          project_total("x", "a", "b", fetch=unreadable)[0] == 0)

    # 8. The project name reaches the query as a value, never as syntax.
    check("a quote in a project name is escaped", sql_literal("a'b") == "'a\\'b'")

    print()
    if fails:
        print("%d check(s) failed." % len(fails))
        return 1
    print("all checks passed.")
    return 0


# --- driver --------------------------------------------------------------------

def report(lad, day, w0, w1):
    n = float(lad["n"])
    print("cohort of %s: %d projects whose first upload to PyPI was that day"
          % (day, lad["n"]))
    print("window: %s .. %s  (days %d-%d after first upload)"
          % (w0, w1, WINDOW_FROM, WINDOW_TO))
    print()
    print("  fetches from installers a person can drive, per project over the window")
    print("  %-22s %6s  %7s" % ("", "count", "share"))
    for r in RUNGS:
        c = lad["rungs"][r]
        print("  at least %-13d %6d  %6.1f%%" % (r, c, 100.0 * c / n))
    print("  %-22s %6d  %6.1f%%"
          % ("none at all", lad["n"] - lad["rungs"][RUNGS[0]],
             100.0 * (lad["n"] - lad["rungs"][RUNGS[0]]) / n))
    print()
    print("  median %s   p90 %s   p99 %s   largest %s   cohort total %s"
          % (lad["p50"], lad["p90"], lad["p99"], lad["max"], lad["total"]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Place a PyPI package's downloads against every package born the same day.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit status: 0 measured and every control agreed, 1 a control "
               "refused, 2 nothing to measure.")
    ap.add_argument("project", nargs="?", help="PyPI project name")
    ap.add_argument("--date", help="skip the project; report the cohort born on this day")
    ap.add_argument("--selftest", action="store_true", help="run the counterexamples offline")
    ap.add_argument("--json", action="store_true", help="print the raw result as JSON")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.project and not args.date:
        ap.error("give a project name, or --date")
    if freshness is None:
        return 1

    # Control 1: is the endpoint answering completely at all?
    f = freshness()
    if not f["reliable"]:
        print("UNRELIABLE: %s" % f["why"])
        for e in f["errors"]:
            print("  %s" % e)
        return 1
    newest = f["latest_day"]
    print("control: %s" % f["why"])
    if f["note"]:
        print("note:    %s" % f["note"])
    print()

    day = args.date
    if day is None:
        day, err = birth_date(args.project, fetch=ask)
        if day is None:
            print("no measurement: %s" % err)
            return 2
        print("%s was first uploaded on %s" % (args.project, day))

    d = _day(day)
    w0 = str(d + datetime.timedelta(days=WINDOW_FROM))
    w1 = str(d + datetime.timedelta(days=WINDOW_TO))

    # Control 2: has the window actually closed?
    ok, why = window_closed(w1, newest)
    print("control: %s" % why)
    if not ok:
        print("UNRELIABLE: refusing to report a rate over a window that is still open.")
        return 1

    # Control 3: is this cohort the size a cohort should be?
    sizes, err = cohort_sizes(
        [str(d - datetime.timedelta(days=1)), day, str(d + datetime.timedelta(days=1))])
    if err:
        print("UNRELIABLE: the cohort sizes did not come back: %s" % err)
        return 1
    ok, why = cohort_plausible(day, sizes)
    print("control: %s" % why)
    if not ok:
        print("UNRELIABLE: refusing to compare against a cohort that looks short.")
        return 1
    print()

    lad, err = ladder(day, w0, w1)
    if lad is None:
        print("no measurement: %s" % err)
        return 2
    report(lad, day, w0, w1)

    result = {"day": day, "window": [w0, w1], "cohort": lad}
    if args.project:
        mine, err = project_total(args.project, w0, w1)
        if err:
            print("\nno measurement for %s itself: %s" % (args.project, err))
            return 2
        rung, cleared, share = place(mine, lad)
        print()
        print("%s: %d over the same window" % (args.project, mine))
        if rung is None:
            print("  below the lowest rung, with %d of %d others (%.1f%%)"
                  % (cleared, lad["n"], 100.0 * share))
        else:
            print("  clears 'at least %d', which %d of %d others also clear (%.1f%%)"
                  % (rung, cleared, lad["n"], 100.0 * share))
        print()
        print("  Read this as an upper bound on people, not a count of them: one")
        print("  person's CI is many fetches, and a crawler that names itself pip")
        print("  is counted here as a person could be.")
        result["project"] = {"name": args.project, "person_possible": mine,
                             "rung": rung, "share_clearing": share}

    if args.json:
        print()
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
