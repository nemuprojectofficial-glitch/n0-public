#!/usr/bin/env python3
"""How many of your PyPI downloads were people?

    python3 real_downloads.py <your-package-name>

No install, no account, no API key, no dependencies beyond the standard
library. It asks PyPI's own public download log — which records, for every
download, *which installer asked* — and splits your headline number into the
part a person could have been at the end of and the part that could not.

Most of the number is usually not people. That is normal and it is not your
fault; it is what the number is. This prints the other one.

---------------------------------------------------------------------------
What this file is, and what it is not

This is a front end. Every measurement and every judgement call below lives in
`reach_probe.py`, next to this file: the query, the installer classification,
and the control that decides whether the endpoint's answer can be trusted at
all. This file only asks for one package and lays the answer out for the person
who published it.

That split is deliberate. `reach_probe.py` has a counterexample suite
(`python3 reach_probe.py --selftest`) and its classification is arguable in the
open: every installer on the not-a-person side is printed with the one-line
reason it is there, so you can disagree with a specific line rather than with a
number. Nothing here re-derives any of that.
---------------------------------------------------------------------------
"""

import datetime
import sys

try:
    import reach_probe
except ImportError:                                            # pragma: no cover
    sys.exit("real_downloads.py needs reach_probe.py in the same directory.\n"
             "  curl -sO https://raw.githubusercontent.com/"
             "nemuprojectofficial-glitch/n0-public/main/reach_probe.py")


# A person who wants to know "are these real" is asking about recent history,
# not about all time. Thirty days is long enough to survive a quiet week and
# short enough that a release from a year ago is not still carrying the number.
DEFAULT_DAYS = 30


def _fmt(n):
    return "{:,}".format(n)


def _bar(fraction, width=28):
    filled = int(round(fraction * width))
    return "#" * filled + "." * (width - filled)


def report(project, rows, days, ci_rows=None, ci_error=None, out=sys.stdout):
    """Lay out one package's split. Pure formatting — no network, no judgement.

    `rows` is what reach_probe.by_day returns: dicts with installer and count.
    """
    split = reach_probe.classify(rows)
    person = split["person_possible_total"]
    robot = split["not_a_person_total"]
    headline = person + robot

    w = out.write
    w("\n")
    w("  {}  —  last {} days\n".format(project, days))
    w("  " + "=" * 62 + "\n\n")

    if headline == 0:
        w("  No downloads recorded in this window.\n\n")
        w("  If you know that is wrong, read A-ZERO-THAT-MEANS-UNKNOWN.md in\n"
          "  this repository before believing it — this dataset has a way of\n"
          "  answering 0 when it means 'I stopped reading'. This tool sends\n"
          "  the parameter that turns that case into an error instead, so a 0\n"
          "  here is more likely to be real than one you get by hand.\n\n")
        return split

    pct = 100.0 * person / headline
    w("  headline  (the number on the badge)        {:>12}\n".format(_fmt(headline)))
    w("  could have been a person                   {:>12}   {:.1f}%\n"
      .format(_fmt(person), pct))
    w("  [{}]\n\n".format(_bar(person / headline)))

    if split["person_possible"]:
        w("  the person-possible side\n")
        for inst, n in sorted(split["person_possible"].items(),
                              key=lambda kv: -kv[1]):
            w("    {:<24} {:>12}   {:>5.1f}%\n"
              .format(inst or "(none)", _fmt(n), 100.0 * n / headline))
        w("\n")

    if split["not_a_person"]:
        w("  the rest, and why each one is not a person\n")
        for inst, n in sorted(split["not_a_person"].items(),
                              key=lambda kv: -kv[1]):
            why = reach_probe.NOT_A_PERSON.get(
                inst, "not an installer a person drives")
            label = inst if inst else "(no installer header)"
            w("    {:<24} {:>12}   {:>5.1f}%   {}\n"
              .format(label, _fmt(n), 100.0 * n / headline, why))
        w("\n")

    if split["unparsed"]:
        w("  {} row(s) had a count this tool could not read. They are left out\n"
          "  of every number above rather than counted as zero.\n\n"
          .format(len(split["unparsed"])))

    # The sentence the person came for. It is deliberately not a grade.
    w("  " + "-" * 62 + "\n")
    if pct < 5:
        w("  Under 5% of this number could have been a person.\n")
    elif pct < 25:
        w("  About {:.0f}% of this number could have been a person.\n".format(pct))
    else:
        w("  {:.0f}% could have been a person, which is high for this dataset.\n"
          .format(pct))
    w("  'Could have been' is the honest ceiling, not an estimate of humans.\n\n")

    # Second cut: the log's own CI flag. Until 2026-09-19 this tool stopped at
    # the line above and said, in as many words, that the pip figure could not
    # be split further. It can. The paragraph that said otherwise was wrong,
    # and it was wrong for every reader who ran this before that date.
    w("  " + "-" * 62 + "\n")
    if ci_error:
        w("  CI split: not available for this package.\n\n")
        w("    {}\n\n".format(ci_error))
        w("  The download log carries a `ci` flag, but only on its event-level\n"
          "  table — one row per download. For a large package over a long\n"
          "  window that scan exceeds the endpoint's read limit and is refused\n"
          "  outright, which is the safe outcome: a truncated scan would have\n"
          "  quietly under-counted instead. Try a shorter --days.\n\n"
          "  This line is printed rather than skipped on purpose. A missing\n"
          "  CI figure that is not explained reads as 'no CI here'.\n\n")
    elif ci_rows is not None:
        c = reach_probe.classify_ci(ci_rows)
        total = c["person_possible_total"]
        if total == 0:
            w("  CI split: the event-level table returned no person-possible\n"
              "  rows for this window, so there is nothing to split.\n\n")
        else:
            share = 100.0 * c["declared_ci"] / total
            w("  Of the {} that could have been a person, the log says:\n\n"
              .format(_fmt(total)))
            w("    declared CI          {:>12}   {:>5.1f}%\n"
              .format(_fmt(c["declared_ci"]), share))
            w("    did not declare CI   {:>12}   {:>5.1f}%\n"
              .format(_fmt(c["not_ci"]), 100.0 * c["not_ci"] / total))
            if c["ci_unknown"]:
                w("    unclassified         {:>12}   {:>5.1f}%\n"
                  .format(_fmt(c["ci_unknown"]), 100.0 * c["ci_unknown"] / total))
            w("\n")
            remaining = c["not_ci"] + c["ci_unknown"]
            if c["declared_ci"]:
                w("  So the person-possible figure above is at most {}, not {}.\n"
                  .format(_fmt(remaining), _fmt(person)))
            else:
                w("  Nothing in this window declared itself CI, so the figure\n"
                  "  above does not move. That is an answer, not a missing one.\n")
            w("  'Did not declare CI' is still a ceiling, not a headcount:\n"
              "  a Docker build or a dependency bot that sets no CI variable\n"
              "  lands in it. It is a lower ceiling than the one above, which\n"
              "  is the whole of what this line claims.\n\n")
    else:
        w("  CI split: not requested.\n\n")
    return split


# Rows actually returned by the endpoint on 2026-09-16, kept so the layout can
# be seen and tested without a network — and so the example in the README is a
# measurement rather than an illustration. Not a fixture invented to look good:
# this is a real package with a real, unflattering answer.
DEMO_ROWS = [
    {"date": "2026-09-11", "installer": "",             "count": "163"},
    {"date": "2026-09-11", "installer": "Browser",      "count": "57"},
    {"date": "2026-09-11", "installer": "requests",     "count": "35"},
    {"date": "2026-09-11", "installer": "bandersnatch", "count": "22"},
    {"date": "2026-09-11", "installer": "pip",          "count": "11"},
    {"date": "2026-09-12", "installer": "bandersnatch", "count": "22"},
    {"date": "2026-09-12", "installer": "Browser",      "count": "10"},
    {"date": "2026-09-12", "installer": "",             "count": "3"},
    {"date": "2026-09-13", "installer": "bandersnatch", "count": "8"},
    {"date": "2026-09-13", "installer": "Browser",      "count": "7"},
    {"date": "2026-09-13", "installer": "",             "count": "2"},
    {"date": "2026-09-14", "installer": "bandersnatch", "count": "4"},
    {"date": "2026-09-14", "installer": "",             "count": "3"},
    {"date": "2026-09-15", "installer": "bandersnatch", "count": "8"},
    {"date": "2026-09-15", "installer": "",             "count": "4"},
    {"date": "2026-09-15", "installer": "requests",     "count": "3"},
]

# The CI half of the same demo, measured 2026-09-19 from pypi.pypi for the same
# package. The window there is 2026-09-11..17 rather than ..15, which for this
# package makes no difference to the person-possible side: pip is 11 in both.
# Stated rather than quietly relied on, because "the windows are the same" is
# the kind of thing that stops being true without anyone noticing.
DEMO_CI_ROWS = [
    {"installer": "",             "ci": "false", "count": "179"},
    {"installer": "Browser",      "ci": "false", "count": "79"},
    {"installer": "bandersnatch", "ci": "false", "count": "72"},
    {"installer": "requests",     "ci": "false", "count": "38"},
    {"installer": "pip",          "ci": "false", "count": "11"},
]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help"):
        # Name the command the way it was actually invoked. Installed from PyPI
        # this is `real-downloads`; curled next to reach_probe.py it is
        # `python3 real_downloads.py`. Printing the wrong one is a small lie
        # that costs the reader a minute at the exact moment they are deciding
        # whether this thing works.
        import os
        prog = os.path.basename(sys.argv[0] or "real_downloads.py")
        how = prog if prog.startswith("real-downloads") else "python3 " + prog
        sys.stdout.write(__doc__ + "\n"
                         "  {0} <package> [--days N]\n"
                         "  {0} --demo\n\n".format(how))
        return 0

    if argv[0] == "--demo":
        report("agent-audit-ledger", DEMO_ROWS, 5, ci_rows=DEMO_CI_ROWS)
        sys.stdout.write(
            "  (--demo replays rows measured on 2026-09-16, and a CI split\n"
            "   measured on 2026-09-19. No network was used. Run it against\n"
            "   your own package for a live answer.)\n\n"
            "  This package happens to have no declared-CI traffic, which is\n"
            "  why that block does not move the number. It is not always so\n"
            "  quiet: over the same week, 6,008 of pypistats' own 16,548\n"
            "  person-possible downloads — 36% — declared themselves CI.\n\n")
        return 0

    project = argv[0]
    # PEP 503. The download log stores only the normalized name, and the name
    # PyPI *shows* you is not it: asked in the same minute on 2026-09-18,
    # 'Django' returned 0 rows and 'django' returned 23,925,705 downloads. Until
    # this line existed, typing your package's name the way its own PyPI page
    # spells it got you a confident zero. Say so out loud rather than quietly
    # substituting.
    asked = reach_probe.normalize(project)
    if asked != project:
        sys.stdout.write(
            "\n  asking about '{}' — PyPI's download log stores names\n"
            "  normalized (PEP 503), and only that form is in it.\n"
            .format(asked))
    days = DEFAULT_DAYS
    if "--days" in argv:
        try:
            days = int(argv[argv.index("--days") + 1])
        except (IndexError, ValueError):
            sys.exit("--days needs a whole number of days")

    # The control first, always. This endpoint can return the aggregate of a
    # truncated scan with HTTP 200 and no warning, and a truncated read always
    # under-reports — so the failure mode points at "nobody downloaded this",
    # which is exactly the conclusion you are here to draw. Asking a package
    # that cannot be small, and refusing to print if the answer about *it*
    # comes back small, is the cheapest way to notice.
    fresh = reach_probe.freshness()
    if not fresh["reliable"]:
        sys.stderr.write(
            "\n  Not printing a number.\n\n"
            "  The check that runs before every measurement did not pass:\n"
            "    {}\n\n".format(fresh["why"] or "unknown"))
        for e in fresh["errors"]:
            sys.stderr.write("    {}\n".format(e))
        sys.stderr.write(
            "\n  A number from this endpoint when the control is failing is\n"
            "  not a small number, it is an unknown one. See\n"
            "  A-ZERO-THAT-MEANS-UNKNOWN.md.\n\n")
        return 2

    # Count back from the log's newest day, not from today. Today is one to two
    # days ahead of this dataset, and anchoring on it silently shortens the
    # window by the lag — which, again, only ever makes the answer smaller.
    newest = datetime.date.fromisoformat(fresh["latest_day"])
    since = str(newest - datetime.timedelta(days=days - 1))

    rows, err = reach_probe.by_day(project, since=since)
    if err:
        sys.stderr.write("\n  Could not read the download log: {}\n\n".format(err))
        return 2

    if not rows:
        sys.stdout.write(
            "\n  {}: no rows in the download log for {} onward.\n\n"
            "  This is not 'nobody downloaded it'. Three things return the\n"
            "  same empty answer, and only one of them is about your users:\n\n"
            "    1. The name. The log is keyed on the PEP 503 normalized form\n"
            "       ('{}'), not on the name PyPI displays. That substitution\n"
            "       already happened above, so it is not this — unless the\n"
            "       package is spelled differently from what you typed.\n"
            "    2. The lag. This dataset runs one to two days behind, so a\n"
            "       package released today is empty here for a while.\n"
            "    3. Nobody, and nothing, has fetched a file of it in {} days.\n\n"
            "  Check https://pypi.org/project/{}/ resolves before reading\n"
            "  this as (3).\n\n"
            .format(project, since, asked, days, asked))
        return 0

    # The CI split is asked for separately because it can legitimately fail
    # while the figures above are fine — see reach_probe.by_installer_and_ci.
    # A failure here must not take the rest of the answer down with it, and
    # must not be swallowed either; report() prints whichever happened.
    ci_rows, ci_err = reach_probe.by_installer_and_ci(project, since=since)
    report(asked, rows, days, ci_rows=None if ci_err else ci_rows, ci_error=ci_err)
    sys.stdout.write(
        "  window: {} to {} (the log's newest day, not today)\n"
        "  source: PyPI's public download log, read through ClickHouse's free\n"
        "          demo endpoint. Nothing here is written; no key is sent.\n\n"
        .format(since, fresh["latest_day"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
