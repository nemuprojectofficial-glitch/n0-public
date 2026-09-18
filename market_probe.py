#!/usr/bin/env python3
"""market_probe.py — point the PyPI download log at *other people's* packages.

No dependencies. Python 3.8+. Read-only: HTTPS GET only, no credentials, no
cookies, no request body, nothing written anywhere.

Why this exists
---------------
`reach_probe.py` (next to this file) answers "did anyone take *my* package?".
That is a mirror. This project ran mirrors for fifty-eight sessions and then
noticed that every instrument it owned was pointed at itself.

This one asks the question one step earlier, and about everyone else:

    for a named category of packages, how many installs could have been a
    person — and is the category I am standing in inhabited at all?

That matters because "nobody downloaded mine" has two very different causes,
and a mirror cannot separate them:

    the category has no users              -> the product is the problem
    the category has users, mine has none  -> the distribution is the problem

You cannot tell those apart by looking at your own number. You can tell them
apart by looking at your neighbours'.

What it reads
-------------
The same free, read-only SQL endpoint `reach_probe.py` documents:

    https://sql-clickhouse.clickhouse.com/?user=demo
    pypi.pypi_downloads_per_day_by_version_by_installer_by_type

`user=demo` is that service's published read-only role, not anyone's credential.

Two shapes of question, and why they are not equally trustworthy
----------------------------------------------------------------
**Named** (`--names a,b,c`) filters on an explicit list, which this endpoint
answers completely. Its weakness is the list: it can only contain names you
already knew, so it can never tell you the category is empty — only that the
names you thought of are.

**Discovery** (`--like`) asks the index instead, which can return names you did
not know. Its weakness is that the endpoint caps execution time and, on
overflow, **returns the partial result of the timed-out scan with HTTP 200 and
no warning** (measured; see reach_probe.py). A pattern scan is exactly the shape
that overflows.

So the two are used asymmetrically, and the tool enforces it:

    a discovery hit  ->  evidence that something exists
    a discovery miss ->  evidence of nothing at all

`--like` therefore runs a **canary**: a project whose count this run has already
established by a named query, and whose name matches the pattern, must come back
from the pattern query with the same number. If it is missing or short, the
pattern result is marked TRUNCATED and every absence in it is worthless.

★ Measured 2026-09-14, and it is worse than "sometimes short"
--------------------------------------------------------------
On this endpoint, pattern queries came back **completely empty, with HTTP 200
and an empty body**. Same table, same date literal, same installer set; the one
thing changed was `project IN (...)` -> `project ILIKE '...'`:

    project IN ('langsmith', ...)   on 2026-09-13  ->  langsmith  1,475,675
    project ILIKE '%langsmith%'     on 2026-09-13  ->  (no rows)

Three pattern queries were run that day and all three returned nothing. So a
discovery run here does not merely under-report: **its silence carries no
information at all**, and a tool that printed "0 projects found" from it would
be reporting an emptiness that is not in the data.

This is why the canary is not optional and why it must be a *pattern* query
whose answer is already known by a complete read. Without it, this run would
have recorded "the agent x audit niche on PyPI is empty" as a measurement. That
sentence would have been false, and nothing in the HTTP response would have
said so.

The mechanism is not asserted here. What was measured is the behaviour.

The reliability control is `reach_probe.freshness()`, unchanged and reused: a
reference project too large to be small is asked for its newest day first, and
nothing below is reported as a measurement if that comes back short or stale.

Two rooms
---------
Measured 2026-09-14 from this project's sandbox:

    sql-clickhouse.clickhouse.com -> Tunnel connection failed: 403 Forbidden

The endpoint is outside the sandbox's allowlist, and inside the CI runner's.
So `--print-urls` emits the exact GET URLs for a run, each labelled with which
query it is, to be fetched from the other room and read there. Nothing about the
queries changes; only who performs the GET.

Each query pins its own day with a *filtered* subquery
(`SELECT max(date) ... WHERE project = 'requests'`) rather than an unfiltered
`max(date)`, and every row carries the day it used — so a set of answers fetched
in one batch cannot silently straddle two different days.
"""

import argparse
import json
import sys

import reach_probe as rp

PERSON = sorted(rp.PERSON_POSSIBLE)


def _person_sql_set():
    return "(" + ", ".join(rp.sql_literal(i) for i in PERSON) + ")"


# The day, expressed as a *filtered* subquery. An unfiltered `max(date)` over
# this table is the read that was measured returning a stale answer with HTTP
# 200 and no warning; filtering by one project is the read that is complete.
NEWEST_DAY = ("(SELECT max(date) FROM {d} WHERE project = {p})"
              .format(d=rp.DAILY, p=rp.sql_literal(rp.REFERENCE_PROJECT)))


def build_sql(names_a, names_b, names_c, must, any_of, limit=100):
    """Every statement of one run, labelled. Built once, so the URLs handed to
    the other room and the queries run here cannot drift apart."""
    allnames = list(dict.fromkeys(names_a + names_b + names_c))

    def named_sql(projects):
        return (
            "SELECT date AS day, project AS p, sum(count) AS c FROM {t} "
            "WHERE date = {day} AND project IN ({pl}) AND installer IN {il} "
            "GROUP BY date, project ORDER BY c DESC"
        ).format(t=rp.TABLE, day=NEWEST_DAY, il=_person_sql_set(),
                 pl=", ".join(rp.sql_literal(p) for p in projects))

    clauses = ["project ILIKE {}".format(rp.sql_literal("%" + must + "%"))]
    if any_of:
        clauses.append("(" + " OR ".join(
            "project ILIKE {}".format(rp.sql_literal("%" + a + "%")) for a in any_of) + ")")
    disc = (
        "SELECT date AS day, project AS p, sum(count) AS c FROM {t} "
        "WHERE date = {day} AND {w} AND installer IN {il} "
        "GROUP BY date, project ORDER BY c DESC LIMIT {n}"
    ).format(t=rp.TABLE, day=NEWEST_DAY, w=" AND ".join(clauses),
             il=_person_sql_set(), n=int(limit))

    return [
        # ★ This must stay the summed form. It was written as the one-row
        # `LIMIT 1` read — a copy of the defect being fixed in reach_probe.py on
        # the same day, made in the same hour, by copying the line rather than
        # calling it. A control duplicated is a control that will drift.
        ("freshness", "SELECT date AS d, sum(count) AS c FROM {} WHERE project = {} "
                      "GROUP BY date ORDER BY date DESC LIMIT 1"
                      .format(rp.DAILY, rp.sql_literal(rp.REFERENCE_PROJECT))),
        ("unfiltered_scan", "SELECT max(date) AS d FROM {}".format(rp.TABLE)),
        ("list_a", named_sql(names_a)),
        ("list_b", named_sql(names_b)),
        ("list_c", named_sql(names_c)),
        ("ever_in_log", "SELECT DISTINCT project AS p FROM {t} WHERE project IN ({pl})"
                        .format(t=rp.TABLE,
                                pl=", ".join(rp.sql_literal(p) for p in allnames))),
        ("discovery", disc),
    ]


def named(projects, day, fetch=rp.ask):
    """Person-possible downloads on `day`, per project, for an explicit list.

    Filtered read: this endpoint answers these completely. A project absent from
    the result had no person-possible download that day (or does not exist);
    both are reported as 0, and the caller is told which by `--check-exists`.
    """
    if not projects:
        return {}, None
    in_list = "(" + ", ".join(rp.sql_literal(p) for p in projects) + ")"
    sql = (
        "SELECT project AS p, sum(count) AS c FROM {t} "
        "WHERE date = {d} AND project IN {pl} AND installer IN {il} "
        "GROUP BY project ORDER BY c DESC"
    ).format(t=rp.TABLE, d=rp.sql_literal(day), pl=in_list, il=_person_sql_set())
    rows, err = fetch(sql, timeout=60)
    if err:
        return {}, err
    out = {}
    for r in rows:
        try:
            out[r["p"]] = int(r["c"])
        except (KeyError, TypeError, ValueError):
            continue
    for p in projects:
        out.setdefault(p, 0)
    return out, None


def exists(projects, fetch=rp.ask):
    """Which of these names have ever appeared in the log at all.

    Separates "the package has no users today" from "I made the name up".
    Without this, a stale list quietly reports the category as empty.
    """
    if not projects:
        return set(), None
    in_list = "(" + ", ".join(rp.sql_literal(p) for p in projects) + ")"
    sql = (
        "SELECT DISTINCT project AS p FROM {t} WHERE project IN {pl}"
    ).format(t=rp.TABLE, pl=in_list)
    rows, err = fetch(sql, timeout=60)
    if err:
        return set(), err
    return {r["p"] for r in rows if "p" in r}, None


def discover(day, must, any_of, limit=100, fetch=rp.ask):
    """Ask the index for names matching a pattern. Truncation is possible.

    `must` is required in the name; `any_of` is a list of which at least one
    must also appear. Both are matched case-insensitively.

    ★ The patterns are PEP 503 normalized first. ILIKE already handles case, but
    it does not handle separators, and the log stores only `-`: searching for
    `zope.interface` or `flask_sql` returns nothing at all while the packages sit
    right there under `zope-interface` and `flask-sql…`. An empty result set from
    a search is read as "nobody is doing this", which is the one conclusion this
    file exists to make harder to reach by accident.
    """
    must = rp.normalize(must)
    any_of = [rp.normalize(a) for a in any_of]
    clauses = ["project ILIKE {}".format(rp.sql_literal("%" + must + "%"))]
    if any_of:
        ors = " OR ".join(
            "project ILIKE {}".format(rp.sql_literal("%" + a + "%")) for a in any_of)
        clauses.append("(" + ors + ")")
    sql = (
        "SELECT project AS p, sum(count) AS c FROM {t} "
        "WHERE date = {d} AND {w} AND installer IN {il} "
        "GROUP BY project ORDER BY c DESC LIMIT {n}"
    ).format(t=rp.TABLE, d=rp.sql_literal(day), w=" AND ".join(clauses),
             il=_person_sql_set(), n=int(limit))
    rows, err = fetch(sql, timeout=60)
    if err:
        return [], err
    out = []
    for r in rows:
        try:
            out.append((r["p"], int(r["c"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out, None


def canary(found, known, must, any_of):
    """Decide whether a pattern result may be used for absence.

    `known` maps project -> count established by a *named* (complete) query.
    Any of those whose name matches the pattern must reappear here with the
    same count. Returns (ok, why).
    """
    def matches(name):
        n = name.lower()
        if must.lower() not in n:
            return False
        return (not any_of) or any(a.lower() in n for a in any_of)

    expect = {p: c for p, c in known.items() if matches(p) and c > 0}
    if not expect:
        return False, ("no project whose count is already known by a complete read "
                       "matches this pattern, so there is nothing to check the "
                       "pattern read against. Absence here proves nothing.")
    got = dict(found)
    bad = []
    for p, c in sorted(expect.items()):
        if p not in got:
            bad.append("%s missing (complete read said %d)" % (p, c))
        elif got[p] != c:
            bad.append("%s came back %d, complete read said %d" % (p, got[p], c))
    if bad:
        return False, "; ".join(bad)
    return True, ("%d canary project(s) reappeared with identical counts: %s"
                  % (len(expect), ", ".join(sorted(expect))))


def selftest():
    """Falsify each judgement this file makes. A tool that has only printed
    pass has demonstrated nothing."""
    ok = True

    def check(name, cond):
        nonlocal ok
        print("%-5s %s" % ("pass" if cond else "FAIL", name))
        if not cond:
            ok = False

    # The download log holds PEP 503 names and nothing else, so a search term
    # carrying a dot or an underscore has to be converted before it is asked, or
    # it matches nothing and the nothing reads as an absence of packages.
    seen = []

    def capture(sql, timeout=60):
        seen.append(" ".join(sql.split()))
        return [], None

    discover("2026-09-11", "zope.interface", ["Flask_SQL"], 10, fetch=capture)
    asked = seen[0] if seen else ""
    check("a search pattern is normalized before it reaches ILIKE",
          "'%zope-interface%'" in asked and "'%flask-sql%'" in asked and
          "zope.interface" not in asked)

    # canary: a matching known project that reappears identically -> usable
    good, why = canary([("agent-tracer", 500), ("x", 1)],
                       {"agent-tracer": 500}, "agent", ["trace"])
    check("canary passes when the known project reappears with the same count", good)

    # canary: short count -> truncated
    bad, why = canary([("agent-tracer", 499)], {"agent-tracer": 500}, "agent", ["trace"])
    check("canary fails when the pattern read under-reports a known project", not bad)

    # canary: missing -> truncated
    bad, why = canary([], {"agent-tracer": 500}, "agent", ["trace"])
    check("canary fails when a known matching project is absent", not bad)

    # canary: nothing to check against -> refuse, do not silently pass
    bad, why = canary([("a", 1)], {"requests": 9}, "agent", ["trace"])
    check("canary refuses when no known project matches the pattern", not bad)

    # canary must not be satisfied by a known project with zero count
    bad, why = canary([], {"agent-trace": 0}, "agent", ["trace"])
    check("a known project with zero count is not a usable canary", not bad)

    # named(): absent projects come back as 0, not missing
    def fake(sql, timeout=30):
        return [{"p": "alpha", "c": "7"}], None
    got, err = named(["alpha", "beta"], "2026-09-01", fetch=fake)
    check("named() reports an unseen project as 0 rather than dropping it",
          got == {"alpha": 7, "beta": 0} and err is None)

    # named(): an endpoint error is returned, never rendered as zeros
    def dead(sql, timeout=30):
        return [], "boom"
    got, err = named(["alpha"], "2026-09-01", fetch=dead)
    check("named() returns the error instead of reporting zeros", err == "boom" and got == {})

    # the person-possible set is the one reach_probe publishes, not a copy
    check("the installer classification is reach_probe's, not a second copy",
          set(PERSON) == set(rp.PERSON_POSSIBLE))

    print("\n%s" % ("all checks passed" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--names", default="",
                    help="comma-separated project list (complete, trustworthy read)")
    ap.add_argument("--label", default="named", help="a name for that list")
    ap.add_argument("--like", default="",
                    help="substring every discovered name must contain")
    ap.add_argument("--like-any", default="",
                    help="comma-separated; a discovered name must contain one of these too")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--day", default="", help="override the day (default: newest reliable)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--print-urls", action="store_true",
                    help="emit the GET URLs for a full run, to be fetched from a "
                         "room that can reach the endpoint")
    ap.add_argument("--names-b", default="", help="second list, for --print-urls")
    ap.add_argument("--names-c", default="", help="third list, for --print-urls")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()

    if a.print_urls:
        sp = lambda s: [x.strip() for x in s.split(",") if x.strip()]
        stmts = build_sql(sp(a.names), sp(a.names_b), sp(a.names_c),
                          a.like, sp(a.like_any), a.limit)
        for label, sql in stmts:
            print("# %s" % label)
            print(rp.q(sql))
        return 0

    fresh = rp.freshness()
    if not a.day and not fresh["reliable"]:
        print("UNRELIABLE: %s" % fresh["why"], file=sys.stderr)
        if fresh["note"]:
            print("  note: %s" % fresh["note"], file=sys.stderr)
        return 2
    day = a.day or fresh["latest_day"]

    # ★ The download log is keyed on the PEP 503 normalized name and holds no
    # other form, so a name typed the way PyPI's project page shows it — with
    # capitals, an underscore or a dot — matches nothing and comes back as
    # "never in log". That is a wrong answer shaped exactly like a right one.
    # Normalize here, at the boundary, and say so when the form changed.
    typed = [n.strip() for n in a.names.split(",") if n.strip()]
    names = list(dict.fromkeys(rp.normalize(n) for n in typed))
    changed = [(t, rp.normalize(t)) for t in typed if t != rp.normalize(t)]
    if changed and not a.json:
        for t, n in changed:
            print("name: asked for %r as %r (PEP 503; the log holds no other "
                  "form)" % (t, n), file=sys.stderr)
    counts, err = named(names, day)
    if err:
        print("named read failed: %s" % err, file=sys.stderr)
        return 2
    seen, err2 = exists(names) if names else (set(), None)

    result = {
        "day": day,
        "reliable": fresh["reliable"],
        "reference": {"project": fresh["reference_project"],
                      "count": fresh["latest_day_count"],
                      "why": fresh["why"]},
        "person_possible_installers": PERSON,
        "named": {"label": a.label,
                  "counts": counts,
                  "never_in_log": sorted(set(names) - seen) if names else [],
                  "exists_error": err2},
        "discovery": None,
    }

    if a.like:
        any_of = [x.strip() for x in a.like_any.split(",") if x.strip()]
        found, err3 = discover(day, a.like, any_of, a.limit)
        usable, why = canary(found, counts, a.like, any_of)
        result["discovery"] = {
            "must_contain": a.like, "any_of": any_of, "limit": a.limit,
            "error": err3, "rows": found,
            "usable_for_absence": usable, "canary": why,
        }

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("day %s  (%s: %s)" % (day, fresh["reference_project"], fresh["why"]))
    print("person-possible installers: %s\n" % ", ".join(PERSON))
    if names:
        print("-- %s (complete read) --" % a.label)
        for p, c in sorted(counts.items(), key=lambda kv: -kv[1]):
            tag = "  (never in the log at all)" if p in result["named"]["never_in_log"] else ""
            print("  %9d  %s%s" % (c, p, tag))
        print()
    if result["discovery"]:
        d = result["discovery"]
        print("-- discovery: name contains %r%s --" % (
            d["must_contain"],
            (" and one of %s" % d["any_of"]) if d["any_of"] else ""))
        if d["error"]:
            print("  read failed: %s" % d["error"])
        for p, c in d["rows"]:
            print("  %9d  %s" % (c, p))
        if not d["rows"] and not d["error"]:
            print("  (no rows came back)")
        print("  %s" % ("USABLE for absence: " if d["usable_for_absence"]
                        else "NOT usable for absence: ") + d["canary"])
        if not d["usable_for_absence"]:
            print("  -> do not write down an emptiness from this. Measured "
                  "2026-09-14: pattern queries on this endpoint returned an "
                  "empty body with HTTP 200 while a complete read of the same "
                  "day returned 1,475,675 for a project the pattern matched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
