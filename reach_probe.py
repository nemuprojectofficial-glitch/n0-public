#!/usr/bin/env python3
"""reach_probe.py — how many of your package's downloads could have been a person.

No dependencies. Python 3.8+. Read-only: HTTPS GET only, no credentials, no
cookies, no request body, nothing written anywhere.

Why this exists
---------------
This project published a package to PyPI and then spent sessions writing
"external reactions: 0" without being able to say whether that zero meant
"nobody wanted it" or "nobody saw it". The denominator was called unmeasurable.

It was not. PyPI logs every file fetch, ships the log to a public dataset, and
one of the columns is the *installer* that asked. So the honest question has an
answer:

    of the fetches of my files, how many could possibly have been a person
    typing `pip install`, and how many could not have been?

The answer is usually humbling. The first day after a release, almost every
fetch is a robot: mirrors, malware scanners, dependency-graph builders, and
"new releases" feeds pull every new file on PyPI within minutes. A raw download
count therefore rises the moment you publish, whether or not anyone wanted it.
**A number that goes up because you acted is not a measurement of anyone else.**

What it reads
-------------
ClickHouse publishes the PyPI download log as a free, read-only SQL endpoint
(no account, no key):

    https://sql-clickhouse.clickhouse.com/?user=demo

    pypi.pypi_downloads_per_day_by_version_by_installer_by_type
        project, version, date, installer, type, count
    pypi.pypi_downloads_per_day_by_version_by_installer_by_type_by_country
        ... + country_code

Neither is this project's data and neither can be written to from here. The
`user=demo` in the URL is that service's published read-only role, not a
credential of anyone's.

★ The control, and why it is not optional
-----------------------------------------
The endpoint **returns the partial result of a truncated scan with HTTP 200 and
no warning**. Measured 2026-09-12:

    SELECT max(date) FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
        -> "2026-09-01"                        (whole table: wrong, silently)

    SELECT max(date) FROM pypi.pypi_downloads_per_day WHERE project = 'requests'
        -> "2026-09-11"                        (filtered: right)

Ten days of data existed and the unfiltered aggregate denied it, successfully.
An instrument that cannot say "I don't know" will say something else instead.

★ Correction, 2026-09-16: this header used to say the cap was on execution
time. It is not. Asking the server directly:

    max_execution_time   60          <- never reached; these die in ~1.3 s
    max_rows_to_read     1000000000
    read_overflow_mode   break       <- this one

The table holds 11,028,536,818 rows, so any scan it cannot answer from the
primary index stops at one billion and returns what it has. Adding
`timeout_overflow_mode=throw` therefore changed nothing, which is how the
mistake was found; `read_overflow_mode=throw` is the parameter that matters,
and it is now sent on every request this tool makes. The sorting key is
`project, version, date, installer`, so a predicate on `project` is an index
seek and a predicate on `date` alone is a full scan of eleven billion rows.
Full write-up and reproduction: A-ZERO-THAT-MEANS-UNKNOWN.md.

So this tool never reports a number on its own. Every run first asks a
*reference* project — one downloaded tens of millions of times a day, so a
small answer about it is impossible rather than merely surprising — for its
newest day and that day's total. If the reference comes back missing, stale, or
implausibly small, the window is marked UNRELIABLE and the run exits non-zero.
Refusing to answer is the feature.

The unfiltered aggregate is still run, and still disagrees, but it is printed as
a known property of this endpoint rather than as a failure. The first version of
this file failed the run on that disagreement, which meant the alarm fired on
every single run, including the correct ones. An alarm that is always on is the
same as no alarm — this project has now built that twice, so the note stays
here: the control has to be something that can come back clean.

How to read the result
----------------------
    could have been a person   installers a human invokes: pip, uv, poetry, ...
                               An upper bound, never a count of people. One
                               person's CI can be a thousand of these.
    could not have been        declared mirrors, browsers fetching the file,
                               bare HTTP libraries, and requests that sent no
                               installer at all.

    "could have been a person" = 0   -> nothing reached anyone. Distribution.
    a flat, decaying curve from
    release day, nothing after       -> you measured the scanners. Still nobody.
    fetches on days with no release  -> the first thing here worth a second look.

What it cannot tell you
-----------------------
  * It counts file fetches, not people, not installs that succeeded, not use.
  * The installer string is self-reported by the client and is not verified.
  * "could have been a person" is an upper bound on people and a lower bound on
    nothing. It is not evidence of demand. It never becomes evidence of demand
    by being large.
  * An empty result means "no rows in this dataset for that window", which is
    not the same as "no downloads" — the daily tables lag the day itself.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://sql-clickhouse.clickhouse.com/"
ROLE = "demo"            # ClickHouse's published read-only demo role, not a credential
TABLE = "pypi.pypi_downloads_per_day_by_version_by_installer_by_type"
TABLE_COUNTRY = TABLE + "_by_country"
DAILY = "pypi.pypi_downloads_per_day"

# A project whose downloads are counted in the tens of millions per day. It is
# here only so the freshness question has an answer that cannot be zero.
REFERENCE_PROJECT = "requests"

# The reference's newest day must clear this. Measured 2026-09-05..09-11, its
# daily total ran 28.4M to 46.0M, so a floor three hundred times below the low
# end cannot be tripped by a quiet weekend — only by a partial read.
REFERENCE_FLOOR = 100_000

# ★ Fixed 2026-09-14. `pypi.pypi_downloads_per_day` holds SEVERAL rows per
# (project, date), not one. This check used to read a single row —
#
#     SELECT date, count ... ORDER BY date DESC LIMIT 1
#
# — and compare that one row against a floor meant for the day's total. Which
# row came back was the endpoint's choice. Measured on 2026-09-13, requests had
# six rows:
#
#     58,700 · 211,622 · 1,892,934 · 5,235,594 · 18,690,653 · 967,122
#     sum = 27,056,625, which equals the installer table's independent sum
#     for the same day, to the digit.
#
# The row that came back was 58,700 — 0.22% of the day — so the control
# declared a complete read unreliable. On 2026-09-11 the same code drew
# 35,081,158 of a true 42,483,582: it passed, and printed a number 17.4% short
# as a fact about the dataset.
#
# So this control failed in both directions, and its own docstring named the
# disease: *an instrument that cannot say "I don't know" will say something
# else instead.* The part that could say "I don't know" was the broken part.
# It now sums the day.

UA = "reach-probe (read-only; github.com/nemuprojectofficial-glitch/n0-public)"

# Installers a person can be at the other end of. Anything not listed is counted
# on the "could not have been a person" side, which is the side that does not
# flatter the number.
PERSON_POSSIBLE = {
    "pip", "uv", "poetry", "pdm", "pipenv", "hatch", "conda", "pex",
    "pip-tools", "rye", "flit", "twine",
}

# Why each of the others cannot be a person, in one line, printed with the count
# so the classification is arguable instead of asserted.
NOT_A_PERSON = {
    "bandersnatch": "declared PyPI mirror",
    "": "sent no installer header (scrapers, CDNs, unattributed automation)",
    "Browser": "a browser fetching the file, not installing it",
    "requests": "a bare HTTP client script",
    "urllib": "a bare HTTP client script",
    "httpx": "a bare HTTP client script",
    "devpi": "caching proxy",
    "artifactory": "caching proxy",
    "nexus": "caching proxy",
    "OS": "operating-system package build, not an end user",
    "Nix": "operating-system package build, not an end user",
    "Homebrew": "operating-system package build, not an end user",
}


def q(sql):
    """Build the read-only URL for one statement."""
    return "{}?{}".format(ENDPOINT, urllib.parse.urlencode({
        "user": ROLE,
        "default_format": "JSONEachRow",
        # See the header: the limit that truncates here is on rows read, not on
        # seconds, and the default overflow mode is "break" — return the
        # fragment, HTTP 200, no warning. "throw" turns that into Code 158,
        # which `ask` returns as an error and the control turns into UNRELIABLE.
        "read_overflow_mode": "throw",
        "query": sql,
    }))


def ask(sql, timeout=30):
    """GET one statement. Returns (rows, error). Never raises for the caller."""
    req = urllib.request.Request(q(sql), method="GET", headers={
        "User-Agent": UA,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:                                 # noqa: BLE001
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


def sql_literal(s):
    """Single-quote a value for ClickHouse. The only untrusted input is a
    project name, and it goes nowhere else."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


# --- the control ---------------------------------------------------------------

def freshness(fetch=ask):
    """Ask a project that cannot be small how fresh and how complete this is.

    Returns a dict. `reliable` is False when the reference is missing, or its
    newest day's total falls under REFERENCE_FLOOR — which is what a partial
    read looks like from the outside, since a truncated scan under-reports and
    never over-reports.
    """
    ref, err1 = fetch(
        "SELECT date AS d, sum(count) AS c FROM {} WHERE project = {} "
        "GROUP BY date ORDER BY date DESC LIMIT 1"
        .format(DAILY, sql_literal(REFERENCE_PROJECT)))
    whole, err2 = fetch("SELECT max(date) AS d FROM {}".format(TABLE))

    ref_day = ref[0].get("d") if ref else None
    try:
        ref_count = int(ref[0].get("c")) if ref else None
    except (TypeError, ValueError):
        ref_count = None
    whole_day = whole[0].get("d") if whole else None

    out = {
        "reference_project": REFERENCE_PROJECT,
        "latest_day": ref_day,
        "latest_day_count": ref_count,
        "latest_day_unfiltered_scan": whole_day,
        "errors": [e for e in (err1, err2) if e],
        "reliable": False,
        "why": "",
        "note": "",
    }
    # Since 2026-09-16 every request carries read_overflow_mode=throw, so the
    # unfiltered scan — which is deliberately a query this endpoint cannot
    # complete — now comes back as Code 158 instead of as a quiet wrong date.
    # That is the *healthy* outcome and must not be filed under "errors", or the
    # tool would report a fault every run for doing exactly what it intended.
    if err2 and ("TOO_MANY_ROWS" in err2 or "Code: 158" in err2):
        out["errors"] = [e for e in (err1,) if e]
        out["note"] = (
            "the unfiltered scan of the same table refused to answer "
            "(TOO_MANY_ROWS), which is correct: it would have had to read more "
            "than max_rows_to_read (1e9) of this table's 1.1e10 rows. Before "
            "read_overflow_mode=throw was sent, that same query returned the "
            "aggregate of the first billion rows with HTTP 200 and no warning. "
            "Filtered reads on the sorting key (project) are complete and are "
            "what every number below comes from. See A-ZERO-THAT-MEANS-UNKNOWN.md.")
    elif whole_day and ref_day and whole_day != ref_day:
        out["note"] = (
            "the unfiltered scan of the same table says its newest day is {}, "
            "while asking about one project says {}. This endpoint stops a scan "
            "at max_rows_to_read (1e9) and, with read_overflow_mode=break, "
            "returns the aggregate of the fragment with HTTP 200 and no warning, "
            "so whole-table aggregates here are not usable. Filtered reads on "
            "the sorting key (project) are. See A-ZERO-THAT-MEANS-UNKNOWN.md."
            .format(whole_day, ref_day))
    if err1 or ref_day is None:
        out["why"] = ("{} returned nothing. Either the endpoint is not answering "
                      "or the dataset moved; no number below is a measurement."
                      .format(REFERENCE_PROJECT))
        return out
    if ref_count is None:
        out["why"] = ("{} returned a day but no readable count, so completeness "
                      "cannot be checked.".format(REFERENCE_PROJECT))
        return out
    if ref_count < REFERENCE_FLOOR:
        out["why"] = ("{} reports only {:,} downloads on {}, far under the {:,} "
                      "floor. A truncated read under-reports, so the numbers "
                      "below are probably short too."
                      .format(REFERENCE_PROJECT, ref_count, ref_day, REFERENCE_FLOOR))
        return out
    if whole_day and whole_day > ref_day:
        out["why"] = ("the unfiltered scan reaches {} but the reference stops at "
                      "{}, which is backwards: the reference read is the stale "
                      "one.".format(whole_day, ref_day))
        return out
    out["reliable"] = True
    out["why"] = ("{} reports {:,} downloads on {}, so the data reaches that day "
                  "and is not a partial read."
                  .format(REFERENCE_PROJECT, ref_count, ref_day))
    return out


# --- classification ------------------------------------------------------------

def classify(rows):
    """Split installer rows into what could and could not have been a person.

    `rows` are dicts with `installer` and `count`. Counts arrive from ClickHouse
    as strings; a row whose count will not parse is dropped into `unparsed`
    rather than silently read as zero.
    """
    person, robot, unparsed = {}, {}, []
    for row in rows:
        inst = row.get("installer")
        if inst is None:
            inst = ""
        try:
            n = int(row.get("count"))
        except (TypeError, ValueError):
            unparsed.append(row)
            continue
        bucket = person if inst in PERSON_POSSIBLE else robot
        bucket[inst] = bucket.get(inst, 0) + n
    return {
        "person_possible": person,
        "not_a_person": robot,
        "person_possible_total": sum(person.values()),
        "not_a_person_total": sum(robot.values()),
        "unparsed": unparsed,
    }


# --- measurement ---------------------------------------------------------------

def by_day(project, since=None, fetch=ask):
    where = "project = {}".format(sql_literal(project))
    if since:
        where += " AND date >= toDate({})".format(sql_literal(since))
    return fetch(
        "SELECT date AS date, installer AS installer, sum(count) AS count "
        "FROM {} WHERE {} GROUP BY date, installer ORDER BY date ASC LIMIT 1000"
        .format(TABLE, where))


def by_country(project, since=None, fetch=ask):
    where = "project = {}".format(sql_literal(project))
    if since:
        where += " AND date >= toDate({})".format(sql_literal(since))
    return fetch(
        "SELECT country_code AS country_code, installer AS installer, "
        "sum(count) AS count FROM {} WHERE {} GROUP BY country_code, installer "
        "ORDER BY count DESC LIMIT 100".format(TABLE_COUNTRY, where))


# --- offline self-test ---------------------------------------------------------

def selftest():
    """Counterexamples, run without a network. Each one must fail the way it is
    supposed to fail; a check that only ever passes is not a check."""
    fails = []

    def check(name, ok):
        print("  %-58s %s" % (name, "ok" if ok else "FAILED"))
        if not ok:
            fails.append(name)

    # 1. The real shape of the first day after a release: 288 fetches, 11 of
    #    which a person could have caused.
    day1 = [
        {"installer": "", "count": "163"},
        {"installer": "Browser", "count": "57"},
        {"installer": "requests", "count": "35"},
        {"installer": "bandersnatch", "count": "22"},
        {"installer": "pip", "count": "11"},
    ]
    c = classify(day1)
    check("a release day splits 11 / 277",
          c["person_possible_total"] == 11 and c["not_a_person_total"] == 277)

    # 2. An unknown installer must land on the robot side, not the person side.
    c = classify([{"installer": "some-new-crawler", "count": "900"}])
    check("an unknown installer is not counted as a person",
          c["person_possible_total"] == 0 and c["not_a_person_total"] == 900)

    # 3. A count that will not parse is reported, not read as zero.
    c = classify([{"installer": "pip", "count": None}])
    check("an unreadable count is held aside, not rounded to 0",
          c["person_possible_total"] == 0 and len(c["unparsed"]) == 1)

    # 4. The live endpoint really does disagree with itself. That is a property
    #    of the endpoint, not a fault in the window, so it must be *reported*
    #    without failing the run — otherwise the alarm is on during every
    #    correct run, which is the same as having no alarm.
    def live_shape(sql, timeout=30):
        if "WHERE project" in sql:
            return [{"d": "2026-09-11", "c": "42483582"}], None
        return [{"d": "2026-09-01"}], None
    f = freshness(fetch=live_shape)
    check("the endpoint's known self-disagreement is noted, not failed",
          f["reliable"] is True and "max_rows_to_read" in f["note"])

    # 4b. With read_overflow_mode=throw the unfiltered scan now *refuses*. That
    #     is the intended behaviour, so it must not be reported as a fault, and
    #     it must not drag the run to unreliable. Added 2026-09-16 together with
    #     the parameter, because the same shape passed the old check by
    #     accident: an error there simply left `note` empty and nobody looked.
    def refuses_whole_scan(sql, timeout=30):
        if "WHERE project" in sql:
            return [{"d": "2026-09-11", "c": "42483582"}], None
        return [], ("HTTPError 500: Code: 158. DB::Exception: Limit for rows or "
                    "bytes to read exceeded, max rows: 1.00 billion, current "
                    "rows: 9.03 billion (TOO_MANY_ROWS)")
    f = freshness(fetch=refuses_whole_scan)
    check("a refused whole-table scan is the healthy case, not an error",
          f["reliable"] is True and f["errors"] == [] and "TOO_MANY_ROWS" in f["note"])

    # 5. A reference that comes back small is what a partial read looks like,
    #    and it must fail — this is the check that can actually say no.
    def truncated(sql, timeout=30):
        if "WHERE project" in sql:
            return [{"d": "2026-09-11", "c": "412"}], None
        return [{"d": "2026-09-11"}], None
    f = freshness(fetch=truncated)
    check("a reference under the floor fails the run",
          f["reliable"] is False and "far under" in f["why"])

    # 6. A dead endpoint is not a clean bill of health.
    def dead(sql, timeout=30):
        return [], "URLError: unreachable"
    check("an unreachable endpoint is unreliable, not reliable",
          freshness(fetch=dead)["reliable"] is False)

    # 6b. A reference older than the unfiltered scan means the reference itself
    #     is the stale read, and nothing below it can be trusted either.
    def backwards(sql, timeout=30):
        if "WHERE project" in sql:
            return [{"d": "2026-09-01", "c": "42483582"}], None
        return [{"d": "2026-09-11"}], None
    check("a reference older than the whole-table scan fails",
          freshness(fetch=backwards)["reliable"] is False)

    # 6c. ★ The regression this control shipped with until 2026-09-14: the
    #     reference day is made of several rows, and reading one of them is not
    #     reading the day. The fixture answers the way the live endpoint does —
    #     one row per fetch unless the statement aggregates — so the check can
    #     only pass if the statement asks for the sum.
    def per_day_is_many_rows(sql, timeout=30):
        if "WHERE project" not in sql:
            return [{"d": "2026-09-13"}], None
        rows = [58700, 211622, 1892934, 5235594, 18690653, 967122]
        if "sum(count)" in sql and "GROUP BY date" in sql:
            return [{"d": "2026-09-13", "c": str(sum(rows))}], None
        return [{"d": "2026-09-13", "c": str(rows[0])}], None      # one arbitrary row
    f = freshness(fetch=per_day_is_many_rows)
    check("the reference day is summed, not sampled from one of its rows",
          f["reliable"] is True and f["latest_day_count"] == 27056625)

    # 7. The project name reaches the query as a value, never as syntax.
    check("a quote in a project name is escaped",
          sql_literal("a'b") == "'a\\'b'")

    print()
    if fails:
        print("%d check(s) failed." % len(fails))
        return 1
    print("all checks passed.")
    return 0


# --- driver --------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="How many of a PyPI package's downloads could have been a person.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit status: 0 measured and the control agreed, 1 the control "
               "disagreed or the data could not be read, 2 bad usage.")
    ap.add_argument("project", nargs="?", help="PyPI project name")
    ap.add_argument("--since", metavar="YYYY-MM-DD", help="only days at or after this")
    ap.add_argument("--country", action="store_true", help="also break down by country")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--selftest", action="store_true",
                    help="run the offline counterexamples and exit")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.project:
        ap.error("give a PyPI project name, or --selftest")

    control = freshness()
    rows, err = by_day(args.project, args.since)

    days = {}
    for r in rows:
        days.setdefault(r.get("date"), []).append(r)
    per_day = {d: classify(rs) for d, rs in days.items()}
    overall = classify(rows)

    countries = []
    if args.country and not err:
        countries, cerr = by_country(args.project, args.since)
        if cerr:
            countries = []

    if args.as_json:
        print(json.dumps({
            "project": args.project,
            "control": control,
            "error": err,
            "per_day": {d: {k: v for k, v in c.items() if k != "unparsed"}
                        for d, c in per_day.items()},
            "overall": {k: v for k, v in overall.items() if k != "unparsed"},
            "by_country": countries,
        }, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if (control["reliable"] and not err) else 1

    print("=" * 72)
    print("project: %s" % args.project)
    print("control: %s" % ("OK" if control["reliable"] else "UNRELIABLE"))
    print("         %s" % control["why"])
    if control["note"]:
        print("  note:  %s" % control["note"])
    for e in control["errors"]:
        print("         error: %s" % e)
    print("=" * 72)

    if err:
        print("could not read the download log: %s" % err)
        return 1
    if not rows:
        print("no rows for this project in the window.")
        print("that is 'the daily tables have nothing here yet', not 'no downloads'.")
        return 0 if control["reliable"] else 1

    print("%-12s %14s %18s" % ("day", "could be a person", "could not be"))
    for d in sorted(per_day):
        c = per_day[d]
        print("%-12s %14d %18d" % (d, c["person_possible_total"], c["not_a_person_total"]))
    print("-" * 72)
    print("%-12s %14d %18d" % ("total", overall["person_possible_total"],
                               overall["not_a_person_total"]))
    print()

    if overall["person_possible"]:
        print("could have been a person (upper bound on people, not a count of them):")
        for k, v in sorted(overall["person_possible"].items(), key=lambda kv: -kv[1]):
            print("  %-22s %8d" % (k or "(none)", v))
    else:
        print("could have been a person: nothing. No installer a human drives")
        print("appears in this window at all.")
    print()
    print("could not have been a person:")
    for k, v in sorted(overall["not_a_person"].items(), key=lambda kv: -kv[1]):
        print("  %-22s %8d   %s" % (k or "(no installer header)", v,
                                    NOT_A_PERSON.get(k, "not an installer a human drives")))

    if overall["unparsed"]:
        print()
        print("%d row(s) had a count that would not parse and were left out."
              % len(overall["unparsed"]))

    if countries:
        print()
        print("by country (top %d rows):" % len(countries))
        for r in countries[:25]:
            inst = r.get("installer") or "(none)"
            mark = "person?" if inst in PERSON_POSSIBLE else "       "
            print("  %-4s %-22s %8s  %s" % (r.get("country_code"), inst,
                                            r.get("count"), mark))

    print()
    print("Read this as fetches of files, not as people and not as use.")
    print("On the days right after a release, almost all of it is automation")
    print("that would have fetched anything published at that moment.")

    return 0 if control["reliable"] else 1


if __name__ == "__main__":
    sys.exit(main())
