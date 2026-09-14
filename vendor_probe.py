#!/usr/bin/env python3
"""
vendor_probe.py — what is sold, and what is given away, in one neighbourhood of PyPI.

The question this answers
-------------------------
A previous probe (``market_probe.py``) measured *how many people install* the
packages that sit next to mine. It found that the neighbourhood is not empty:
the largest neighbour is downloaded over a million times a day. That is
adoption, and adoption is not payment. The obvious next column, and the one
that had never been measured here, is:

    In this neighbourhood, what does anyone actually put money on?

Not "is there demand" — "what is the priced object". A pricing page states,
in public, what its author believes someone will pay for. Twenty-two of them
side by side say what the *shape* of a paid thing is in this area, which is a
different question from whether any particular vendor is succeeding.

Why it matters to whoever is reading this
-----------------------------------------
If you are deciding whether to build a library in some area, the thing you
most want to know early is whether a library is the kind of object that
carries a price there — or whether the price always attaches to something
else, and the library is the free part that leads to it. That is knowable
before you write any code, from pages that are already public, and it takes
about four minutes to measure.

What this script does and does not do
-------------------------------------
It does not fetch anything. It holds the roster and the decision rules, and
it classifies text you have already fetched, so that the judgement is in
version control rather than in someone's head.

    python3 vendor_probe.py --urls              # the pages to GET
    python3 vendor_probe.py --classify DIR      # DIR/<name>.txt -> table

The mechanical rule (``has_price``) is deliberately crude and is stated in
full below, because a crude rule that is written down beats a subtle one that
is not. Two columns — whether a *self-hosted* tier carries a number, and what
the price is metered on — cannot be decided by a regex over marketing copy;
those are read by hand, and the rule is that the line they were read from is
quoted in the output. A judgement without its evidence line is not recorded.

The failure this is built against
---------------------------------
A pricing page is a JavaScript application. A GET can return HTTP 200, a
content-length of 800 KB, and no prices at all — not because the vendor has
no prices, but because the numbers arrive in a later request. That refusal and
a genuine absence of price look identical downstream, and the difference is the
whole measurement. So ``UNREADABLE`` is a verdict of its own here, it is never
folded into "no price", and it is printed as its own count. An instrument that
cannot say "I don't know" will say something else instead.
"""

import argparse
import json
import os
import re
import sys

# --------------------------------------------------------------------------
# The roster. Fixed before the first GET, and identical to the download table
# in market_probe.py's last run: nothing added, nothing dropped. Adding a name
# after seeing results would let the roster be chosen by the answer.
# --------------------------------------------------------------------------

# List A: the vocabulary people actually search in — observing, tracing and
# evaluating LLM systems.
LIST_A = [
    "langsmith", "langfuse", "openinference-instrumentation", "braintrust",
    "deepeval", "traceloop-sdk", "opik", "ragas", "weave", "arize-phoenix",
    "literalai", "agentops", "promptlayer", "trulens-eval", "humanloop",
]

# List B: the vocabulary I had been standing in — audit trails, history,
# provenance.
LIST_B = [
    "django-simple-history", "sigstore", "django-auditlog",
    "sqlalchemy-continuum", "django-pghistory", "in-toto", "immudb-py",
]

# Where the price, if any, is stated. Every URL here was reached from the
# project's own PyPI metadata (home_page, project_urls, or a link in the
# rendered description) — never from memory of what a company is called.
PAGES = {
    "langsmith": "https://www.langchain.com/pricing",
    "langfuse": "https://langfuse.com/pricing",
    "openinference-instrumentation": "https://arize.com/pricing/",
    "braintrust": "https://www.braintrust.dev/pricing",
    "deepeval": "https://www.confident-ai.com/pricing",
    "traceloop-sdk": "https://www.traceloop.com/pricing",
    "opik": "https://www.comet.com/site/pricing/",
    "ragas": "https://www.ragas.io/",
    "weave": "https://wandb.ai/site/pricing/",
    "arize-phoenix": "https://arize.com/pricing/",
    "literalai": "https://getliteral.ai/",
    "agentops": "https://www.agentops.ai/",
    "promptlayer": "https://www.promptlayer.com/pricing",
    "trulens-eval": "https://www.trulens.org/",
    "humanloop": "https://humanloop.com/pricing",
    "django-simple-history": "https://django-simple-history.readthedocs.io/en/stable/",
    "sigstore": "https://sigstore.github.io/sigstore-python/",
    "django-auditlog": "https://github.com/jazzband/django-auditlog",
    "sqlalchemy-continuum": "https://sqlalchemy-continuum.github.io/",
    "django-pghistory": "https://django-pghistory.readthedocs.io",
    "in-toto": "https://in-toto.io",
    "immudb-py": "https://codenotary.com/pricing",
}

# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

# Below this many characters of stripped text, the page did not render for a
# machine and the verdict is UNREADABLE, never "no price".
MIN_TEXT = 500

# A nonzero amount with a currency marker. "$0", "Free" and a bare "0" do not
# count: a free tier is the opposite of the thing being measured.
PRICE = re.compile(
    r"(?:\$|US\$|€|£|¥)\s?([0-9][0-9,]*(?:\.[0-9]+)?)"
    r"|([0-9][0-9,]*(?:\.[0-9]+)?)\s?(?:USD|EUR|JPY|GBP)\b"
)

# Text that belongs to the host, not to the project. A repository page on
# GitHub carries GitHub's own navigation, which says "Pricing" and "Enterprise"
# on every repository in the world; counting that would give every community
# project a price it does not have.
HOST_CHROME = (
    "GitHub Copilot", "GitHub Advanced Security", "Codespaces",
    "GitHub Sponsors Fund open source developers",
)


def has_price(text):
    """(verdict, evidence) for the mechanical column."""
    if len(text.strip()) < MIN_TEXT:
        return "UNREADABLE", "stripped text was %d characters" % len(text.strip())
    for m in PRICE.finditer(text):
        amount = (m.group(1) or m.group(2) or "").replace(",", "")
        try:
            if float(amount) == 0:
                continue
        except ValueError:
            continue
        start = max(0, m.start() - 60)
        line = " ".join(text[start:m.end() + 60].split())
        if any(c in line for c in HOST_CHROME):
            continue
        return "PRICED", line
    return "NO PRICE", "no nonzero currency amount in %d characters" % len(text)


# --------------------------------------------------------------------------
# The rule, checked against the cases it exists to get right. Each of these is
# a page shape that was actually met on 2026-09-14; "github chrome" and "free
# tier only" both fired for real, on django-auditlog and traceloop.
# --------------------------------------------------------------------------

CASES = [
    ("a free tier is not a price",
     "Free Forever To check things out $0 / mo Up to 50K spans" + " x" * 300,
     "NO PRICE"),
    ("a real price is a price",
     "Pro for teams $249 / month billed monthly" + " x" * 300,
     "PRICED"),
    ("an unrendered page is not an absence of price",
     "Loading...",
     "UNREADABLE"),
    ("the host's navigation is not the tenant's price",
     "GitHub Copilot Write better code with AI $9 per month" + " x" * 300,
     "NO PRICE"),
    ("a thousands separator does not hide the amount",
     "Enterprise $10,900 /month 100 projects" + " x" * 300,
     "PRICED"),
]


def selftest():
    bad = 0
    for name, text, want in CASES:
        got, _ = has_price(text)
        if got != want:
            bad += 1
        print("  %-4s %-48s -> %s (want %s)"
              % ("ok" if got == want else "FAIL", name, got, want))
    missing = [n for n in LIST_A + LIST_B if n not in PAGES]
    if missing:
        bad += 1
        print("  FAIL roster entries with no page: %s" % ", ".join(missing))
    print("%d cases, %d failed" % (len(CASES), bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--urls", action="store_true",
                    help="print the pages to GET, one per line")
    ap.add_argument("--classify", metavar="DIR",
                    help="classify DIR/<name>.txt for every name in the roster")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--selftest", action="store_true",
                    help="run the rule against its own counter-examples")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.urls:
        seen = set()
        for name in LIST_A + LIST_B:
            url = PAGES[name]
            if url not in seen:
                seen.add(url)
                print(url)
        return 0

    if not args.classify:
        ap.print_help()
        return 2

    rows, missing = [], []
    for name in LIST_A + LIST_B:
        path = os.path.join(args.classify, name + ".txt")
        if not os.path.exists(path):
            missing.append(name)
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        verdict, evidence = has_price(text)
        rows.append(dict(name=name, list="A" if name in LIST_A else "B",
                         url=PAGES[name], verdict=verdict, evidence=evidence))

    if args.json:
        print(json.dumps(dict(rows=rows, missing=missing), ensure_ascii=False, indent=2))
        return 0

    for group in ("A", "B"):
        sub = [r for r in rows if r["list"] == group]
        print("\nlist %s — %d projects" % (group, len(sub)))
        for r in sub:
            print("  %-32s %-10s %s" % (r["name"], r["verdict"], r["evidence"][:90]))
        for verdict in ("PRICED", "NO PRICE", "UNREADABLE"):
            n = sum(1 for r in sub if r["verdict"] == verdict)
            print("  %-10s %d" % (verdict, n))
    if missing:
        print("\nnot classified (no saved text): %s" % ", ".join(missing))
        print("These are not 'no price'. They are not measured.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
