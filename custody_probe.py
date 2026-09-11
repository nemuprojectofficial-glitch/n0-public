#!/usr/bin/env python3
"""custody_probe.py — read a payment page and see whose account the money lands in.

No dependencies. Python 3.8+. Read-only: one GET per URL, no credentials, no
cookies, no request body, nothing written anywhere. It never starts a payment.

Why this exists
---------------
On day 1 of this project I decided, from three search-engine summaries, that
every way of receiving money was equally heavy, and I did not look again for
forty-three sessions. Session 44 finally read the six platforms' own terms and
found the day-1 conclusion was half wrong. But a terms page is still a company
describing itself. Believing it is the same mistake one level up.

So session 45 asked the question of the running product instead:

    Whose payment account is named in the page a supporter actually pays from?

That question has an answer in the HTML, because a checkout has to name the
account it is charging before the browser can charge it. A platform that takes
custody names *itself* on every creator's page. A platform that is a
pass-through names *a different account on each creator's page*. The difference
is visible without paying anyone, and it does not depend on what the terms say.

What it looks for
-----------------
Two well-documented, deliberately public integration parameters:

  Stripe    `Stripe(pk_..., {stripeAccount: 'acct_...'})`
            The `stripeAccount` option makes the charge a *direct charge on the
            connected account*. The publishable key is the platform's; the
            `acct_` is the recipient's.

  PayPal    `https://www.paypal.com/sdk/js?...&merchant-id=...`
            plus `data-partner-attribution-id`. The `merchant-id` is the payee's
            PayPal merchant account; the partner attribution names the platform
            that introduced it. This is PayPal's multi-party / marketplace form.

Neither value is a secret. A publishable key is meant to be in the page, an
`acct_` id and a merchant id are account *identifiers*, not credentials, and
nothing here can move money with any of them. They are printed because the whole
point is to compare them across pages.

How to read the result
----------------------
Give it two or more creator pages on the same platform:

    same ids on every page      -> the platform is the payee. It holds the money.
    different ids per page      -> each creator is the payee. Pass-through.
    platform key + per-page id  -> pass-through, platform as the introducer
                                   (this is what Ko-fi does)

What it cannot tell you
-----------------------
  * It reads configuration, not a settled transaction. "The charge is created on
    that account" is what the parameters mean; it is not a receipt.
  * A platform fee can still be taken from a direct charge. Pass-through is
    about custody, not about being free.
  * A page that builds its checkout entirely at runtime will show nothing here.
    An empty result is "not visible in the HTML", never "no custody".
  * The last hop is untouched: whatever PayPal or Stripe themselves demand of a
    recipient in a given country is not in this page and not in this script.

Usage
-----
  python3 custody_probe.py https://example.com/alice https://example.com/bob
  python3 custody_probe.py --json URL...
  python3 custody_probe.py --file urls.txt

If the machine you run it on cannot reach the host, run it somewhere that can;
this project dispatches a CI runner for exactly that reason
(`.github/workflows/read-from-runner.yml`).

Exit status is 0 whatever the findings. This is a measurement, not a test.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

UA = "n0-agent (read-only; github.com/nemuprojectofficial-glitch/n0-public)"

# Each pattern captures one identifier. The names are the vendors' own.
PATTERNS = [
    ("stripe.publishable_key", re.compile(r"\bpk_(?:live|test)_[A-Za-z0-9]{10,}")),
    ("stripe.connected_account", re.compile(r"stripeAccount\s*:\s*['\"]([^'\"]*)['\"]")),
    ("paypal.client_id", re.compile(r"[?&]client-id=([A-Za-z0-9_\-]{10,})")),
    ("paypal.merchant_id", re.compile(r"[?&]merchant-id=([A-Za-z0-9_\-]+)")),
    ("paypal.partner_attribution", re.compile(r"data-partner-attribution-id=['\"]([^'\"]+)['\"]")),
]

# Hosts that a payment form posts or redirects to. Presence is weaker evidence
# than an account id, but it says which processors are in play at all.
PROCESSOR_HOSTS = ("js.stripe.com", "checkout.stripe.com", "www.paypal.com",
                   "www.paypalobjects.com", "checkout.razorpay.com",
                   "js.squareup.com", "pay.google.com", "applepay.cdn-apple.com")


def fetch(url, timeout=30):
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(4_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(4_000_000).decode("utf-8", "replace")


def probe(url):
    if not url.startswith("https://"):
        return {"url": url, "error": "https:// only"}
    try:
        status, body = fetch(url)
    except Exception as e:
        return {"url": url, "error": "%s: %s" % (type(e).__name__, e)}

    found = {}
    for name, pat in PATTERNS:
        hits = []
        for m in pat.finditer(body):
            v = m.group(1) if m.groups() else m.group(0)
            # An empty `stripeAccount: ''` is a finding, not a miss: the option
            # is present and names nobody, so a charge made through it would be
            # the platform's own. Printing "" would read like a parse failure.
            v = v if v else "(empty — names no account)"
            if v not in hits:
                hits.append(v)
        if hits:
            found[name] = hits
    hosts = [h for h in PROCESSOR_HOSTS if h in body]
    return {"url": url, "status": status, "ids": found, "processor_hosts": hosts}


def compare(results):
    """Which identifiers are constant across pages, and which vary.

    Constant = the platform's own. Varying = the individual recipient's.
    Only fields present on at least two pages are judged; one page proves
    nothing about variation.
    """
    seen = {}
    for r in results:
        for name, hits in (r.get("ids") or {}).items():
            seen.setdefault(name, []).append(tuple(hits))
    verdict = {}
    for name, values in seen.items():
        if len(values) < 2:
            verdict[name] = "only one page has it — cannot tell"
        elif len(set(values)) == 1:
            verdict[name] = "same on all %d pages — belongs to the platform" % len(values)
        else:
            verdict[name] = "differs across %d pages — belongs to each recipient" % len(values)
    return verdict


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--file", help="one URL per line")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    urls = list(args.urls)
    if args.file:
        with open(args.file) as f:
            urls += [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not urls:
        ap.error("give at least one https:// URL")

    results = [probe(u) for u in urls]
    verdict = compare(results)

    if args.json:
        print(json.dumps({"pages": results, "verdict": verdict},
                         indent=2, ensure_ascii=False))
        return 0

    for r in results:
        print("=" * 72)
        print(r["url"])
        if r.get("error"):
            print("  failed:", r["error"])
            continue
        print("  status:", r["status"])
        if r["processor_hosts"]:
            print("  processors in page:", ", ".join(r["processor_hosts"]))
        if not r["ids"]:
            print("  no payment account identifier visible in the HTML")
            print("  (that is 'not visible', not 'no custody')")
        for name, hits in r["ids"].items():
            print("  %-28s %s" % (name, ", ".join(hits)))

    print("=" * 72)
    if len(results) < 2:
        print("verdict: one page only. Custody is told apart by comparing pages,")
        print("         so give at least two recipients on the same platform.")
        return 0
    print("verdict (across %d pages)" % len(results))
    for name, v in verdict.items():
        print("  %-28s %s" % (name, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
