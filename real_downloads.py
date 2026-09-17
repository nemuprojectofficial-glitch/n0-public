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


def report(project, rows, days, out=sys.stdout):
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
    w("  'Could have been' is the honest ceiling, not an estimate of humans:\n"
      "  CI runners, Docker builds and dependency bots all drive pip too, and\n"
      "  the installer field cannot tell you which of those you are looking at.\n"
      "  The number it replaces was the ceiling on the ceiling.\n\n")
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


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(__doc__ + "\n"
                         "  python3 real_downloads.py <package> [--days N]\n"
                         "  python3 real_downloads.py --demo\n\n")
        return 0

    if argv[0] == "--demo":
        report("agent-audit-ledger", DEMO_ROWS, 5)
        sys.stdout.write(
            "  (--demo replays rows measured on 2026-09-16. No network was\n"
            "   used. Run it against your own package for a live answer.)\n\n")
        return 0

    project = argv[0]
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
            "  PyPI's log only has a project once it has been downloaded at\n"
            "  least once, and this dataset runs one to two days behind, so a\n"
            "  package released today will be empty here for a while.\n\n"
            .format(project, since))
        return 0

    report(project, rows, days)
    sys.stdout.write(
        "  window: {} to {} (the log's newest day, not today)\n"
        "  source: PyPI's public download log, read through ClickHouse's free\n"
        "          demo endpoint. Nothing here is written; no key is sent.\n\n"
        .format(since, fresh["latest_day"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
