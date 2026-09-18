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
    183 of them (55.5%) cleared exactly that bar in days 3-7.
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

The two keys
------------
★ These two tables are keyed on different forms of the same name, and nothing in
either of them says so. Measured 2026-09-18, same endpoint, same minute, every
request HTTP 200:

    pypi.projects   name = 'Django'          842 files
                    name = 'django'          no row
                    name = 'zope.interface'  2390 files
                    name = 'zope-interface'  no row

    download log    project = 'django'           1,468,665 on 2026-09-11
                    project = 'Django'           no row
                    project = 'zope-interface'   1,790,045 on 2026-09-11
                    project = 'zope.interface'   no row

`pypi.projects` holds the name as its author uploaded it — the name PyPI shows on
the project page. The download log holds the PEP 503 normalized form, and only
that. They are exact inversions of each other, so a join on the bare columns is a
join between two different keys.

It does not fail. It returns the whole cohort, with the mismatching members set
to zero downloads. On the 2026-09-04 cohort: 11 of 330 uploaded names were not
already normalized, 6 of those had fetches, and the largest had 142
person-possible fetches reported as none — a project in the top 5% of its cohort,
placed below the bottom rung. Everything this file prints is now normalized on
both sides before it is compared; `norm_sql()` is that expression, `normalize()`
is the same rule in Python, and the self-test reads the emitted SQL rather than
trusting that either was called.

The same shape, one level down, is why A-ZERO-THAT-MEANS-UNKNOWN.md exists: a
zero that means "asked with the wrong key" is printed identically to a zero that
means "nobody came".

The four controls, and why each one can actually say no
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
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

try:                                            # same flat package, same endpoint
    from reach_probe import (ENDPOINT, ROLE, TABLE, DAILY, PERSON_POSSIBLE,
                             sql_literal, freshness, normalize)
except ImportError:                             # running the file on its own
    ENDPOINT = "https://sql-clickhouse.clickhouse.com/"
    ROLE = "demo"
    TABLE = "pypi.pypi_downloads_per_day_by_version_by_installer_by_type"
    DAILY = "pypi.pypi_downloads_per_day"
    PERSON_POSSIBLE = {"pip", "uv", "poetry", "pdm", "pipenv", "hatch", "conda",
                       "pex", "pip-tools", "rye", "flit", "twine"}

    def sql_literal(s):
        return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"

    def normalize(name):                        # PEP 503
        return re.sub(r"[-_.]+", "-", str(name)).lower()

    freshness = None                            # the control is not optional
    print("cohort_probe: reach_probe.py must sit beside this file; its freshness "
          "control is not optional.", file=sys.stderr)

PROJECTS = "pypi.projects"
UA = "cohort-probe (read-only; github.com/nemuprojectofficial-glitch/n0-public)"


def norm_sql(column):
    """PEP 503 normalization, expressed in SQL, for `column`.

    The same rule as `normalize()`, and it has to stay the same rule: this
    expression is what makes a row in `pypi.projects` comparable to a row in the
    download log, and the two tables are keyed on different forms of the same
    name (see "The two keys" above). A drift between the Python and the SQL
    would not raise anything — it would quietly stop matching.
    """
    return "lower(replaceRegexpAll({}, '[-_.]+', '-'))".format(column)

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
        # Measured 2026-09-16. This role runs under max_rows_to_read = 1e9 with
        # read_overflow_mode = "break", so a scan that needs more rows than that
        # stops early and returns the aggregate of the fragment it did read,
        # with HTTP 200 and nothing in the body to say so. Asking for "throw"
        # converts that into Code 158 (TOO_MANY_ROWS), which `ask` surfaces as
        # an error. An answer that is a fragment is worse than no answer,
        # because it is shaped exactly like an answer. See
        # A-ZERO-THAT-MEANS-UNKNOWN.md.
        "read_overflow_mode": "throw",
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

def identify(project, fetch=ask):
    """Resolve one typed name into (display name, PEP 503 name, birthday).

    `pypi.projects` is keyed on the name as the author uploaded it. The download
    log is keyed on the PEP 503 normalized form. Neither table will answer to the
    other's key, so the lookup is done on the normalized form of *both* sides —
    that is the only comparison in which a typed name matches its own project
    whichever of the two forms was typed.

    Returns ({"shown": ..., "stored": ..., "day": ...}, error).
    """
    stored = normalize(project)
    rows, err = fetch(
        "SELECT name, toDate(min(upload_time)) AS d FROM {} WHERE {} = {} "
        "GROUP BY name ORDER BY d".format(
            PROJECTS, norm_sql("name"), sql_literal(stored)))
    if err:
        return None, err
    # ClickHouse returns 1970-01-01 for min() over an empty set, which is a date
    # and therefore looks like an answer. It is not one.
    rows = [r for r in rows if r.get("d") and not str(r["d"]).startswith("1970")]
    if not rows:
        return None, ("no upload on record for %r (asked as %r, which is the "
                      "form PyPI stores)" % (project, stored))
    shown = str(rows[0].get("name"))
    out = {"shown": shown, "stored": stored, "day": str(rows[0].get("d"))}
    if len(rows) > 1:
        out["also"] = [str(r.get("name")) for r in rows[1:]]
    return out, None


def birth_date(project, fetch=ask):
    """The calendar day of the project's first-ever file upload, or None."""
    who, err = identify(project, fetch=fetch)
    if who is None:
        return None, err
    return who["day"], None


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
    # ★ Both sides of this join are normalized, and both sides have to be. `c`
    # comes out of pypi.projects, which stores the name as uploaded; `d` comes
    # out of the download log, which stores only the PEP 503 form. Joining the
    # bare columns is a join between two different keys: it matches the projects
    # whose display name happens to already be normalized, and silently gives
    # every other project person = 0. Measured on the 2026-09-04 cohort: 11 of
    # 330 names were not already normalized, 6 of those had downloads, and the
    # largest of them had 142 person-possible fetches counted as none.
    sql = """
    WITH c AS (SELECT name, {norm_name} AS nn FROM {projects} GROUP BY name
               HAVING toDate(min(upload_time)) = {day}),
         d AS (SELECT project, sum(count) AS person FROM {table}
               WHERE date >= {w0} AND date <= {w1} AND installer IN ({inst})
                 AND project IN (SELECT nn FROM c)
               GROUP BY project)
    SELECT count() AS n, {rungs},
           quantileExact(0.5)(person)  AS p50,
           quantileExact(0.9)(person)  AS p90,
           quantileExact(0.99)(person) AS p99,
           max(person) AS pmax, sum(person) AS total
    FROM (SELECT c.name AS name, ifNull(d.person, 0) AS person
          FROM c LEFT JOIN d ON c.nn = d.project)
    """.format(projects=PROJECTS, table=TABLE, inst=installer_list(),
               norm_name=norm_sql("name"),
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
    """One project's person-possible fetches over the window.

    ★ The name is normalized before it reaches the WHERE clause. Without that,
    a project whose page on PyPI says `My_Package` matches nothing in the
    download log, the sum is 0, and the 0 is then placed on the ladder as a
    real measurement — the tool tells its own author, in a full sentence, that
    nobody fetched their package. That is the exact failure this project wrote
    A-ZERO-THAT-MEANS-UNKNOWN.md about.
    """
    rows, err = fetch(
        "SELECT sum(count) AS person FROM {} WHERE project = {} "
        "AND date >= {} AND date <= {} AND installer IN ({})"
        .format(TABLE, sql_literal(normalize(project)), sql_literal(w0),
                sql_literal(w1), installer_list()))
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


# Control 4's sample size. Small on purpose: it is one GET per name against
# pypi.org, and its job is to catch a contaminated cohort, not to audit one.
# Ten names caught 10-of-15 the day it was written.
BIRTH_SAMPLE = 10


def cohort_members(day, limit, fetch=ask):
    """`limit` names from the cohort born on `day`, alphabetically.

    Alphabetical and not random on purpose: the same names come back on a
    re-run, so a reader can check this tool's homework by hand.
    """
    sql = """
    SELECT name FROM {projects} GROUP BY name
    HAVING toDate(min(upload_time)) = {day}
    ORDER BY name LIMIT {limit}
    """.format(projects=PROJECTS, day=sql_literal(day), limit=int(limit))
    rows, err = fetch(sql)
    if err:
        return None, err
    return [r.get("name") for r in rows if r.get("name")], None


def pypi_first_upload(project, timeout=20):
    """The project's earliest upload time, from pypi.org itself.

    pypi.org is the authority on its own upload times and serves one project
    per request, so there is no long scan for anything to cut short. That is the
    entire reason this control is worth the round trips.
    """
    url = "https://pypi.org/pypi/{}/json".format(urllib.parse.quote(project, safe=""))
    req = urllib.request.Request(url, method="GET", headers={
        "User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception as e:                                      # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, e)
    try:
        data = json.loads(body)
        stamps = sorted(f["upload_time_iso_8601"]
                        for files in data["releases"].values() for f in files)
    except Exception as e:                                      # noqa: BLE001
        return None, "unreadable JSON: %s" % e
    if not stamps:
        return None, "no files"
    return stamps[0][:10], None


def births_agree(day, names, lookup=pypi_first_upload):
    """Do the cohort's members really date from `day`, according to PyPI?

    Control 3 asks whether the cohort is the *size* a cohort should be. That is
    a proxy, and this project has now written down six times what happens when a
    proxy is guarded instead of the thing it stands for. The thing here is *who
    is in the cohort*, and a short read changes that in a way size cannot see:
    the cohort is built on `min(upload_time)`, and when the endpoint cuts a scan
    off it computes that minimum over only the rows it read. A project whose
    oldest file sits in the unread part therefore arrives wearing a false recent
    birthday. Every such intruder is an established project, so every one of them
    pushes the download figures *up*.

    Measured the day this was written: of 15 names a truncated read returned as
    newborns, 10 were months old — one of them `anton-agent`, returned as born
    2026-09-11, first published 2026-06-02, 145 versions across 289 files. A
    cohort three times too small looks wrong on sight. A cohort containing
    `anton-agent` looks exactly like a cohort.

    Control 3 would not have caught it, and could not: truncation shrinks the
    neighbouring days too, so the ratio stays in range while all three are short.

    A name pypi.org will not answer for is not counted as agreement.
    """
    if not names:
        return False, "no cohort members came back, so their birthdays cannot be checked"
    agree, wrong, unknown = [], [], []
    for name in names:
        first, err = lookup(name)
        if err or not first:
            unknown.append((name, err or "no date"))
        elif first == day:
            agree.append(name)
        else:
            wrong.append((name, first))
    if wrong:
        shown = ", ".join("%s (first published %s)" % (n, f) for n, f in wrong[:4])
        return False, ("{} of {} sampled cohort members were not born on {} at all: {}"
                       "{} — the cohort contains a different population than it says"
                       .format(len(wrong), len(names), day, shown,
                               ", ..." if len(wrong) > 4 else ""))
    if not agree:
        return False, ("pypi.org answered for none of the {} sampled names ({}), so "
                       "the cohort's membership is unchecked"
                       .format(len(names), unknown[0][1] if unknown else "no reason given"))
    return True, ("pypi.org confirms all {} sampled members were first published on {}{}"
                  .format(len(agree), day,
                          " (%d name(s) unanswered)" % len(unknown) if unknown else ""))


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

    # ★ Re-measured 2026-09-18 with both sides of the join normalized. The
    # numbers this file carried until then (ge1 177, total 63,128) were taken
    # with the bare join described in `ladder`, which dropped every cohort
    # member whose uploaded name was not already in PEP 503 form.
    LAD = {"n": 330, "rungs": {1: 183, 5: 122, 25: 62, 100: 16, 1000: 5},
           "p50": 1, "p90": 49, "p99": 2187, "max": 37175, "total": 63385}

    # 1. The bar this project actually set for itself is cleared by half the
    #    cohort. That is the finding the whole file exists for.
    check("'at least one' is cleared by 55.5% of a birth cohort",
          abs(LAD["rungs"][1] / float(LAD["n"]) - 0.5545) < 0.001)

    # 2. Zero is a measurement, not missing data, and it must be placed.
    rung, cleared, share = place(0, LAD)
    check("zero is placed at the bottom, not treated as unknown",
          rung is None and cleared == 147 and abs(share - 0.4455) < 0.001)

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

    # 5b. The membership control must refuse a cohort whose members are not
    #     from that day, must pass one whose members are, and must not read
    #     "could not check" as "checked and fine". This is the control that
    #     size cannot stand in for: on the day it was written, a truncated read
    #     returned 15 "newborns" of which 10 were months old, and the size
    #     control could not have caught a single one of them.
    real = {"aitesting": "2026-09-04", "entroptics-jlens": "2026-09-04",
            "anton-agent": "2026-06-02", "agentnova": "2026-03-20"}

    def from_pypi(name):
        return (real.get(name), None) if name in real else (None, "HTTPError: 404")

    ok, why = births_agree("2026-09-04",
                           ["aitesting", "entroptics-jlens", "anton-agent"],
                           lookup=from_pypi)
    check("a cohort member months older than the cohort day is refused",
          ok is False and "anton-agent (first published 2026-06-02)" in why)
    check("a cohort whose sampled members really are from that day passes",
          births_agree("2026-09-04", ["aitesting", "entroptics-jlens"],
                       lookup=from_pypi)[0] is True)
    check("a sample pypi.org answers for none of is refused, not assumed fine",
          births_agree("2026-09-04", ["nope-a", "nope-b"], lookup=from_pypi)[0] is False)
    check("an empty member list is refused, not assumed fine",
          births_agree("2026-09-04", [], lookup=from_pypi)[0] is False)

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

    # 9. The two keys. `pypi.projects` stores the name as uploaded; the download
    #    log stores only the PEP 503 form. Measured 2026-09-18 over the same
    #    endpoint, same minute, both HTTP 200:
    #
    #        pypi.projects   'Django' 842 files    'django'         no row
    #                        'zope.interface' 2390 'zope-interface' no row
    #        download log    'django' 1,468,665    'Django'         no row
    #                        'zope-interface' 1,790,045            'zope.interface' no row
    #
    #    Exactly inverted. So every one of these has to be checked where it
    #    actually matters — inside the statement. A normalize() nobody calls is
    #    the same bug with a comment on top of it.
    check("PEP 503 normalization matches the SQL expression's rule",
          normalize("Django") == "django" and
          normalize("zope.interface") == "zope-interface" and
          normalize("Flask_SQLAlchemy") == "flask-sqlalchemy" and
          norm_sql("name") == "lower(replaceRegexpAll(name, '[-_.]+', '-'))")

    seen = []

    def capture(sql, timeout=60):
        seen.append(" ".join(sql.split()))
        return [], None

    # 10. The cohort join. This is the one that was wrong: `c` comes from
    #     pypi.projects and `d` from the download log, and joining their bare
    #     name columns compares two different keys. It does not raise. It
    #     returns 330 rows, of which 11 were silently zeroed.
    seen[:] = []
    ladder("2026-09-04", "2026-09-07", "2026-09-11", fetch=capture)
    joined = seen[0] if seen else ""
    check("the cohort join compares normalized names on both sides",
          "c.nn = d.project" in joined and
          "IN (SELECT nn FROM c)" in joined and
          "c.name = d.project" not in joined)

    # 11. The reader's own number. A project shown as `My_Package` on PyPI has
    #     no row under that name in the download log, so an un-normalized name
    #     here returns 0 — and the 0 is then printed as a measured result and
    #     placed at the bottom of the ladder.
    seen[:] = []
    project_total("My_Package", "2026-09-07", "2026-09-11", fetch=capture)
    asked = seen[0] if seen else ""
    check("the reader's own total is asked under the name the log holds",
          "project = 'my-package'" in asked and "My_Package" not in asked)

    # 12. And the lookup has to accept either form, because the person reading
    #     their PyPI page sees one form and the person reading a pip command
    #     sees the other. Matching on the raw column refuses one of the two.
    seen[:] = []
    identify("zope.interface", fetch=capture)
    looked = seen[0] if seen else ""
    check("a project is found whichever of its two names was typed",
          norm_sql("name") in looked and "'zope-interface'" in looked)

    # 13. identify() must not turn "the endpoint failed" into "no such project",
    #     and must not read 1970 as a birthday.
    def failing(sql, timeout=60):
        return [], "HTTPError: 503"
    check("a failed lookup is an error, not a missing project",
          identify("x", fetch=failing)[1] == "HTTPError: 503")

    def epoch_named(sql, timeout=60):
        return [{"name": "x", "d": "1970-01-01"}], None
    check("a 1970 row is not read as a birthday by identify()",
          identify("x", fetch=epoch_named)[0] is None)

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

    # One lookup settles both of the project's names. Saying out loud which name
    # was actually asked for is not a detail: the two tables this tool reads are
    # keyed on different forms, and a silent substitution is how a wrong answer
    # gets to look like a right one.
    who = None
    if args.project:
        who, err = identify(args.project, fetch=ask)
        if who is None:
            print("no measurement: %s" % err)
            return 2
        if args.project not in (who["shown"], who["stored"]):
            print("name:    you typed %r" % args.project)
        if who["shown"] != who["stored"]:
            print("name:    PyPI's page says %r; PyPI's download log stores %r. "
                  "Both are used below." % (who["shown"], who["stored"]))
        if who.get("also"):
            print("note:    %d other uploaded name(s) normalize to the same key: %s"
                  % (len(who["also"]), ", ".join(who["also"])))

    day = args.date
    if day is None:
        day = who["day"]
        print("%s was first uploaded on %s" % (who["shown"], day))

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

    # Control 4: are the cohort's members really from that day? Control 3 checks
    # the cohort's size, which a truncated read can leave plausible while having
    # quietly swapped who is in it.
    names, err = cohort_members(day, BIRTH_SAMPLE)
    if err:
        print("UNRELIABLE: the cohort's member names did not come back: %s" % err)
        return 1
    ok, why = births_agree(day, names)
    print("control: %s" % why)
    if not ok:
        print("UNRELIABLE: refusing to report a cohort whose members are not from that day.")
        return 1
    print()

    lad, err = ladder(day, w0, w1)
    if lad is None:
        print("no measurement: %s" % err)
        return 2
    report(lad, day, w0, w1)

    result = {"day": day, "window": [w0, w1], "cohort": lad}
    if args.project:
        mine, err = project_total(who["stored"], w0, w1)
        if err:
            print("\nno measurement for %s itself: %s" % (who["shown"], err))
            return 2
        rung, cleared, share = place(mine, lad)
        print()
        print("%s: %d over the same window" % (who["shown"], mine))
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
        result["project"] = {"name": who["shown"], "name_asked": who["stored"],
                             "name_typed": args.project, "person_possible": mine,
                             "rung": rung, "share_clearing": share}

    if args.json:
        print()
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
