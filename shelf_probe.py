#!/usr/bin/env python3
"""shelf_probe.py — before you build a thing for a marketplace, ask who is buying that kind of thing.

No dependencies. Python 3.8+. Read-only: HTTPS GET only, no credentials, no
cookies, no request body, nothing written anywhere.

    python3 shelf_probe.py pypi
    python3 shelf_probe.py "linkedin scraper" --limit 50
    python3 shelf_probe.py --selftest
    python3 shelf_probe.py pypi --body saved.json --baseline saved-top.json

Why this exists
---------------
I spent a session measuring a payout road end to end — the platform's revenue
share, its minimum payout, the currency conversion, the fee to move yen into a
bank account — and then found I had nothing to put on the road. So I picked the
obvious thing to build: my own field is package registries, the store has a
`DEVELOPER_TOOLS` category, I would build a package-registry tool.

Before building it I asked the store one question. The answer took four seconds:

    the store holds 62,003 actors
    its hundred most popular have a median of 24,685 users, the smallest 1,602
    searching it for `pypi` returns thousands of matches, dozens of them
      near-identical to the thing I was about to build
    every one of those has 2 users

Two, thirty-seven times over. Three, twice. Seventeen, once.

That is not an empty shelf. It is a full shelf that nobody shops at. The
difference is invisible from the inside — both of them look like "nobody has
done this yet" when you are standing in your editor with the idea in your head —
and it is the whole difference between a product and a hobby.

This file asks that question for any search term, against any shelf, in one
command, before the building starts.

What it does, exactly
---------------------
Two fetches, never one:

    the search    what exists that matches your term
    the baseline  the shelf's most popular listings, whatever they are

The baseline is not decoration. A small number means nothing on its own — the
endpoint might simply not print large ones. Only when the same endpoint, in the
same minute, hands back six-figure user counts for something else does "two
users" become a fact about your category instead of a fact about your
instrument. This tool will not print a verdict without the baseline, and it
says so when the baseline is missing rather than falling back to the number it
has.

What it refuses to do
---------------------
* It does not average. A shelf where one listing has 300,000 users and forty
  have two has a mean that describes nothing real. It prints the distribution.
* It does not treat an absent field as a zero. A field that is not in the
  response is unknown, and unknown is printed as unknown. `createdAt` is not in
  this endpoint's response at all; a tool that quietly read that as "no
  creation date" would report every listing as brand new.
* It does not trust the shelf's own count. This endpoint prints
  `data.count = 50` and then hands back forty items. Both numbers are printed
  here, and when they disagree the disagreement is the finding.
* **It does not tell you a category is open.** A low number is two things at
  once — nobody has built it, or nobody buys it — and nothing in a listing API
  can separate them. What it can do is kill the first reading when the listings
  are already there. That is the useful half, and it is the half that is
  usually missed, because "nobody has built this" is the more flattering of the
  two and arrives first.

Where the numbers come from
---------------------------
`https://api.apify.com/v2/store`, public, no token. `--endpoint` points this at
another shelf; anything that answers with `{"data": {"items": [...]}}` and
per-item `stats` will parse. The field names are Apify's.

Honesty about this file's own testing
-------------------------------------
The parsing below was checked against two complete responses captured on
2026-09-21 — `search=pypi` (91,099 characters) and `search=tiktok` (147,761
characters) — plus the top hundred by popularity. The live HTTP path was
**not** exercised from the machine this was written on, which cannot reach
`api.apify.com` at all; it was exercised from a CI runner, and what came back
is what the parser was built against. `--selftest` runs the judgement calls
against fixtures and needs no network.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://api.apify.com/v2/store"
UA = "shelf-probe (read-only; github.com/nemuprojectofficial-glitch/n0-public)"
TIMEOUT = 30

# The buckets are fixed here rather than computed from the data. A scale that
# moves with the numbers it describes cannot show you that your category sits
# entirely inside its first bucket, which is the thing worth seeing.
BUCKETS = [(0, 1), (2, 9), (10, 99), (100, 999), (1000, 9999),
           (10000, 99999), (100000, None)]

UNKNOWN = "unknown"


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------

def fetch(endpoint, params):
    """GET one page of a store listing. Returns (body, error). Never raises."""
    url = endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        return None, "%s returned HTTP %s" % (url, e.code)
    except Exception as e:                                     # pragma: no cover
        return None, "%s: %s: %s" % (url, type(e).__name__, e)
    if status != 200:
        return None, "%s returned HTTP %s" % (url, status)
    try:
        return json.loads(raw.decode("utf-8", "replace")), None
    except Exception as e:
        return None, "%s answered with something that is not JSON (%s)" % (url, type(e).__name__)


# --------------------------------------------------------------------------
# reading a body — every judgement call in this file lives in here
# --------------------------------------------------------------------------

def read(body):
    """Pull what is printed out of one response. Absent is absent, not zero.

    Returns a dict with:
        total       what the shelf says matches in all (or UNKNOWN)
        count       what the shelf says it returned (or UNKNOWN)
        items       the listings actually present in the response
        mismatch    True when `count` and len(items) disagree
    """
    data = (body or {}).get("data")
    if not isinstance(data, dict):
        return {"total": UNKNOWN, "count": UNKNOWN, "items": [], "mismatch": False}
    items = data.get("items")
    items = items if isinstance(items, list) else []
    total = data.get("total", UNKNOWN)
    count = data.get("count", UNKNOWN)
    mismatch = isinstance(count, int) and count != len(items)
    return {"total": total, "count": count, "items": items, "mismatch": mismatch}


def stat(item, name):
    """One integer out of an item's stats, or None when the shelf did not print it.

    None is not zero. Every caller below has to decide what to do about a None,
    which is the point: a helper that returned 0 here would let "the field is
    missing" and "the value is nothing" be the same number for the rest of the
    program.
    """
    stats = item.get("stats")
    if not isinstance(stats, dict):
        return None
    v = stats.get(name)
    return v if isinstance(v, int) else None


def price_of(item):
    """What this listing charges, in the shelf's own words. ('FREE'|str|None).

    None means the response carried no pricing field — unknown, not free. The
    vocabulary is the shelf's: this endpoint currently says `PAY_PER_EVENT`,
    and the amounts sit under `eventPriceUsd` or, when the price varies by the
    buyer's plan, `eventTieredPricingUsd.<tier>.tieredEventPriceUsd`. I guessed
    those field names from memory once and got all three wrong, so this reads
    whatever string is there rather than checking against a list I remember.
    """
    info = item.get("currentPricingInfo")
    if not isinstance(info, dict):
        return None
    model = info.get("pricingModel")
    return model if isinstance(model, str) else None


def unit_prices(item):
    """Every per-unit USD amount printed for this listing, cheapest tier last.

    Returned as a flat sorted list, because a shelf that prices one listing six
    different ways by buyer tier has no single price, and inventing one by
    taking the first would make listings look comparable that are not.
    """
    info = item.get("currentPricingInfo")
    if not isinstance(info, dict):
        return []
    # The charge events sit one level down, under `pricingPerEvent`, on every
    # listing this was checked against. They are looked for at the top level
    # too, because writing down the one shape I happened to see is exactly the
    # habit that cost me a bet earlier the same day: the vocabulary of somebody
    # else's response is not mine to remember.
    events = info.get("actorChargeEvents")
    if not isinstance(events, dict):
        nested = info.get("pricingPerEvent")
        events = nested.get("actorChargeEvents") if isinstance(nested, dict) else None
    if not isinstance(events, dict):
        return []
    out = []
    for ev in events.values():
        if not isinstance(ev, dict):
            continue
        flat = ev.get("eventPriceUsd")
        if isinstance(flat, (int, float)):
            out.append(float(flat))
        tiers = ev.get("eventTieredPricingUsd")
        if isinstance(tiers, dict):
            for tier in tiers.values():
                if isinstance(tier, dict):
                    p = tier.get("tieredEventPriceUsd")
                    if isinstance(p, (int, float)):
                        out.append(float(p))
    return sorted(out)


def histogram(values):
    """Count values into the fixed buckets. `values` holds ints only."""
    out = []
    for lo, hi in BUCKETS:
        n = sum(1 for v in values if v >= lo and (hi is None or v <= hi))
        out.append(((lo, hi), n))
    return out


def bucket_label(lo, hi):
    if hi is None:
        return "%s+" % "{:,}".format(lo)
    if lo == hi:
        return "{:,}".format(lo)
    return "%s-%s" % ("{:,}".format(lo), "{:,}".format(hi))


# --------------------------------------------------------------------------
# the verdict — deliberately narrow
# --------------------------------------------------------------------------

def verdict(search_users, baseline_users, n_listings):
    """One sentence about what the two distributions do and do not establish.

    The asymmetry here is on purpose. This function is allowed to say a
    category looks crowded-and-unused, because listings that exist and users
    that do not are both printed. It is never allowed to say a category is
    open, because "no listing" and "no buyer" produce the same empty result and
    no listing API can tell them apart.
    """
    if not baseline_users:
        return ("No baseline. A number with no scale beside it is not a finding — "
                "the endpoint may simply not print large ones. Nothing is concluded.")
    top_base = max(baseline_users)
    if not search_users:
        return ("Nothing matching was returned, while the baseline reached %s users. "
                "That is either an untouched category or one nobody shops in, and this "
                "measurement cannot tell those apart. Do not read it as an opening."
                % "{:,}".format(top_base))
    top_search = max(search_users)
    if top_search >= top_base // 10:
        return ("This category reaches %s users against a baseline top of %s. "
                "People are on this shelf for this. Whether they would pay you is a "
                "different question and this does not answer it."
                % ("{:,}".format(top_search), "{:,}".format(top_base)))
    return ("%d listings already exist here and the best-used one has %s users, "
            "against a baseline top of %s from the same endpoint in the same minute. "
            "The supply is built. The demand is not visible. Building listing %d "
            "changes the first number and, on this evidence, not the second."
            % (n_listings, "{:,}".format(top_search), "{:,}".format(top_base),
               n_listings + 1))


# --------------------------------------------------------------------------
# printing
# --------------------------------------------------------------------------

def report(term, search, baseline, out=sys.stdout):
    w = out.write
    s_users = [u for u in (stat(i, "totalUsers") for i in search["items"]) if u is not None]
    s_runs = [r for r in (stat(i, "totalRuns") for i in search["items"]) if r is not None]
    b_users = [u for u in (stat(i, "totalUsers") for i in baseline["items"]) if u is not None]

    w("\n  %r on this shelf\n" % term)
    w("  " + "=" * 68 + "\n\n")

    w("  the shelf says %s listings match; it returned %s\n"
      % (_n(search["total"]), _n(search["count"])))
    if search["mismatch"]:
        w("  ...and handed back %d. The shelf's own count and its own list disagree;\n"
          "     everything below is counted from the list.\n" % len(search["items"]))
    missing = len(search["items"]) - len(s_users)
    if missing:
        w("  %d of %d listings printed no user count. Counted as unknown, not as zero.\n"
          % (missing, len(search["items"])))
    w("\n")

    w("  users per listing\n")
    w("  %-16s %-26s %s\n" % ("", "matching %r" % term, "shelf's most popular"))
    sh, bh = histogram(s_users), histogram(b_users)
    for (rng, sn), (_, bn) in zip(sh, bh):
        lo, hi = rng
        w("  %-16s %-26s %s\n" % (bucket_label(lo, hi),
                                  _bar(sn) if sn else "",
                                  _bar(bn) if bn else ""))
    w("\n")
    w("  %-16s %-26s %s\n" % ("listings read", len(search["items"]), len(baseline["items"])))
    w("  %-16s %-26s %s\n" % ("most users", _n(max(s_users)) if s_users else "-",
                              _n(max(b_users)) if b_users else "-"))
    w("  %-16s %-26s %s\n" % ("median users", _n(_median(s_users)) if s_users else "-",
                              _n(_median(b_users)) if b_users else "-"))
    if s_runs:
        w("  %-16s %-26s %s\n" % ("most runs", _n(max(s_runs)), ""))
        # Only worth saying when the two numbers actually pull apart. On a
        # healthy category the same line would be noise dressed as insight.
        # Not a ratio: a busy category has a huge ratio too, because its users
        # come back. The shape that means "tried and left" is many runs beside
        # an absolutely tiny number of accounts.
        if s_users and max(s_users) < 100 and max(s_runs) >= 100:
            w("\n  Runs far outrunning users is the shape worth looking at: something\n"
              "  run %s times by %s accounts was not ignored. It was tried and left.\n"
              % (_n(max(s_runs)), _n(max(s_users))))
    w("\n")

    # Three groups, not two. A listing that printed no pricing field has not
    # said it is free; it has said nothing, and folding that into "free" would
    # be the exact error this file spends its docstring warning about.
    models = [price_of(i) for i in search["items"]]
    paid = [i for i, m in zip(search["items"], models) if m is not None and m != "FREE"]
    free = [m for m in models if m == "FREE"]
    silent = [m for m in models if m is None]
    if search["items"]:
        w("  %d of %d charge money" % (len(paid), len(search["items"])))
        if free:
            w(", %d %s free" % (len(free), "is" if len(free) == 1 else "are"))
        if silent:
            w(", %d printed no pricing field at all (unknown, not free)" % len(silent))
        w(".\n")
        prices = sorted({p for i in paid for p in unit_prices(i)})
        if prices:
            w("  Per-unit prices run %s to %s USD.\n"
              % (_usd(prices[0]), _usd(prices[-1])))
        else:
            w("  No per-unit amounts printed.\n")
        w("\n")

    w("  " + "-" * 68 + "\n")
    for line in _wrap(verdict(s_users, b_users, len(search["items"]))):
        w("  " + line + "\n")
    w("\n")


def _n(v):
    return "{:,}".format(v) if isinstance(v, int) else str(v)


def _usd(v):
    return ("%.6f" % v).rstrip("0").rstrip(".")


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def _bar(n, width=22):
    return ("#" * min(n, width)) + ("  %d" % n)


def _wrap(text, width=66):
    words, line, out = text.split(), "", []
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word) if line else word
    if line:
        out.append(line)
    return out


# --------------------------------------------------------------------------
# selftest — counterexamples, no network
# --------------------------------------------------------------------------

def selftest(out=sys.stdout):
    w = out.write
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append("%s: got %r, wanted %r" % (name, got, want))
        w("  %-58s %s\n" % (name, "ok" if got == want else "FAILED"))

    w("\n  shelf_probe selftest\n  " + "=" * 50 + "\n\n")

    # A missing field is unknown, and unknown must not become zero. This is the
    # counterexample that matters most: `createdAt` really is absent from this
    # endpoint, and a tool that read absence as a value would have reported
    # every listing in the store as created at the epoch.
    check("missing stats block -> None, not 0", stat({}, "totalUsers"), None)
    check("stats present, field absent -> None", stat({"stats": {"totalRuns": 3}}, "totalUsers"), None)
    check("stats field non-integer -> None", stat({"stats": {"totalUsers": "many"}}, "totalUsers"), None)
    check("stats field zero -> 0, not None", stat({"stats": {"totalUsers": 0}}, "totalUsers"), 0)

    # The shelf's own count is not the length of its own list.
    body = {"data": {"total": 12930, "count": 50, "items": [{"name": "a"}, {"name": "b"}]}}
    r = read(body)
    check("count/len disagreement is flagged", r["mismatch"], True)
    check("items counted from the list, not the count", len(r["items"]), 2)
    r2 = read({"data": {"total": 7, "count": 2, "items": [{"n": 1}, {"n": 2}]}})
    check("count/len agreement is not flagged", r2["mismatch"], False)

    # Garbage in must not become a confident zero.
    check("no data key -> no items", read({})["items"], [])
    check("no data key -> total unknown", read({})["total"], UNKNOWN)
    check("items not a list -> no items", read({"data": {"items": "nope"}})["items"], [])

    # Pricing: absent is unknown, not free.
    check("no pricing block -> None, not FREE", price_of({}), None)
    check("FREE is reported as FREE", price_of({"currentPricingInfo": {"pricingModel": "FREE"}}), "FREE")
    check("unfamiliar model is passed through",
          price_of({"currentPricingInfo": {"pricingModel": "SOMETHING_NEW_IN_2027"}}),
          "SOMETHING_NEW_IN_2027")

    # Tiered prices: all of them, not the first.
    tiered = {"currentPricingInfo": {"actorChargeEvents": {
        "result": {"eventTieredPricingUsd": {
            "FREE": {"tieredEventPriceUsd": 0.004},
            "DIAMOND": {"tieredEventPriceUsd": 0.0008}}},
        "start": {"eventPriceUsd": 0.00005}}}}
    check("every tier and flat price is collected",
          unit_prices(tiered), [0.00005, 0.0008, 0.004])
    # The same events, one level down, where this endpoint actually puts them.
    nested = {"currentPricingInfo": {"pricingPerEvent": tiered["currentPricingInfo"]["actorChargeEvents"]}}
    check("charge events nested under pricingPerEvent are found",
          unit_prices({"currentPricingInfo": {"pricingPerEvent": {
              "actorChargeEvents": tiered["currentPricingInfo"]["actorChargeEvents"]}}}),
          [0.00005, 0.0008, 0.004])
    check("no charge events -> no prices", unit_prices({"currentPricingInfo": {}}), [])

    # Buckets must not silently drop a value.
    vals = [0, 1, 2, 9, 10, 99, 100, 999, 1000, 9999, 10000, 99999, 100000, 611376]
    check("every value lands in exactly one bucket",
          sum(n for _, n in histogram(vals)), len(vals))

    # The verdict's one hard rule: never call a category open.
    v_empty = verdict([], [1602, 24685], 0)
    check("empty result is not called an opening", "opening" in v_empty and "not" in v_empty, True)
    v_none = verdict([2, 2, 17], [], 40)
    check("no baseline -> nothing is concluded", "Nothing is concluded" in v_none, True)
    v_dead = verdict([2] * 37 + [3, 3, 17], [1602, 24685, 611376], 40)
    check("built-but-unused is stated plainly", "supply is built" in v_dead, True)
    v_live = verdict([289502, 57276], [1602, 24685, 611376], 50)
    check("an inhabited category is not called dead", "supply is built" in v_live, False)

    w("\n")
    if failures:
        w("  %d FAILED\n" % len(failures))
        for f in failures:
            w("    " + f + "\n")
        return 1
    w("  all checks passed\n\n")
    return 0


# --------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Ask a marketplace who is buying the kind of thing you are about to build.")
    p.add_argument("search", nargs="?", help="the term to look for on the shelf")
    p.add_argument("--limit", type=int, default=50, help="listings to ask for (default 50)")
    p.add_argument("--endpoint", default=ENDPOINT, help="another shelf's listing endpoint")
    p.add_argument("--body", help="read the search response from a file instead of the network")
    p.add_argument("--baseline", help="read the baseline response from a file")
    p.add_argument("--selftest", action="store_true", help="run the counterexamples and exit")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.search:
        p.error("a search term is required (or --selftest)")

    def load(path, params):
        if path:
            try:
                return json.load(open(path, encoding="utf-8")), None
            except Exception as e:
                return None, "%s: %s: %s" % (path, type(e).__name__, e)
        return fetch(args.endpoint, params)

    search_body, err = load(args.body, {"limit": args.limit, "search": args.search})
    if err:
        sys.stderr.write("could not read the search: %s\n" % err)
        return 2

    # The baseline is fetched even when the search came back empty. An empty
    # search with no baseline is indistinguishable from a broken endpoint, and
    # "I could not reach it" and "it says there is nothing" must not collapse
    # into the same printed line.
    base_body, base_err = load(args.baseline, {"limit": args.limit, "sortBy": "popularity"})
    if base_err:
        sys.stderr.write("could not read the baseline: %s\n"
                         "  Continuing without it. No verdict will be printed.\n" % base_err)
        base_body = {}

    report(args.search, read(search_body), read(base_body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
