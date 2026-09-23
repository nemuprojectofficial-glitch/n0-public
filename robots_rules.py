#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""robots_rules.py — apply a robots.txt the way the host wrote it, wildcards included.

Why this file exists (2026-09-23 / session 110)
-----------------------------------------------
Session 107 put a gate in `read-from-runner.yml` so that the tool obeys the
robots.txt it reads. The gate used `urllib.robotparser` from the standard
library. Session 110 dispatched a GET for

    https://note.com/api/v3/searchs?context=note&q=zorbilax&size=3&start=0

and the gate allowed it. note.com's robots.txt prints, in its `User-agent: *`
group:

    Disallow: /api/*

`urllib.robotparser` does not implement the `*` wildcard inside a path. It
treats the pattern as a literal prefix, so `/api/*` matches only a URL whose
path begins with the four characters `/api/` followed by an asterisk. The
request went out. The host had printed the rule; the gate had read the file;
the rule did not apply.

    >>> import urllib.robotparser as r
    >>> p = r.RobotFileParser(); p.parse(["User-agent: *", "Disallow: /api/*"])
    >>> p.can_fetch("x", "https://note.com/api/v3/searchs")
    True

Counted against the file note.com actually serves, the old gate honoured
**1 of its 19** `User-agent: *` rules — `Disallow: /search`, the only line in
the file with no wildcard in it. The other eighteen were read and discarded,
because a pattern containing `*` can only ever match a URL that contains a
literal asterisk. The gate was not off. It was reporting compliance it
did not have, which is worse: a gate that refuses nothing is visibly useless,
and a gate that refuses the two easiest cases looks like it works.

RFC 9309 (the 2022 standard) defines `*` and `$` in paths and says the most
specific match wins, with allow beating disallow on a tie. This module
implements that. It is deliberately small and deliberately separate, so the
counterexamples below can be run by anyone:

    python3 公開/robots_rules.py --selftest

The same function body is inlined in `.github/workflows/read-from-runner.yml`,
because that workflow has no checkout step and cannot import a file. Two copies
drift, so a gate compares them byte for byte before anything is published
(`運営/robots二重化の検査.py`). A note asking the next session to keep them in
sync would not have survived the next session.
"""

import re
import sys
import urllib.parse

# ---- BEGIN SHARED BLOCK (mirrored verbatim in read-from-runner.yml) ----
def robots_groups(text):
    """Parse robots.txt into [(set of user-agent tokens, [(allow?, pattern), ...])]."""
    groups, agents, rules, collecting = [], [], [], False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if rules:                      # a new group starts after the rules of the last one
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
            collecting = True
        elif field in ("allow", "disallow") and collecting:
            rules.append((field == "allow", value))
    if agents:
        groups.append((agents, rules))
    return groups


def robots_rules_for(text, ua):
    """The rules of the one group that applies to `ua`. RFC 9309 section 2.2.1:
    the most specific matching product token wins; `*` only if nothing else
    matches. Returns [] when the file says nothing about this crawler."""
    ua = (ua or "").lower()
    best, best_len, star = None, -1, None
    for agents, rules in robots_groups(text):
        for token in agents:
            if token == "*":
                if star is None:
                    star = rules
            elif token and token in ua and len(token) > best_len:
                best, best_len = rules, len(token)
    if best is not None:
        return best
    return star if star is not None else []


def robots_pattern_re(pattern):
    """A robots path pattern as a regex. `*` is any run of characters, a
    trailing `$` anchors the end, everything else is literal."""
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    out = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile("^" + out + ("$" if anchored else ""))


def robots_allows(text, ua, url):
    """True when this robots.txt lets `ua` fetch `url`. RFC 9309 section 2.2.2:
    the longest matching pattern decides; allow wins a tie; no match means yes."""
    parts = urllib.parse.urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    verdict, best = True, -1
    for allow, pattern in robots_rules_for(text, ua):
        if pattern == "":
            # "Disallow:" with nothing after it is the explicit permission to
            # fetch everything, and carries no length, so it never outranks a
            # real rule. "Allow:" empty is meaningless; both are skipped here.
            continue
        if not robots_pattern_re(pattern).match(path):
            continue
        weight = len(pattern)
        if weight > best or (weight == best and allow):
            verdict, best = allow, weight
    return verdict
# ---- END SHARED BLOCK ----


# The file note.com served at 2026-09-23T17:23:15Z, kept verbatim so the
# counterexamples below are about a real host's real rules and not about a
# robots.txt written to make this module look right.
NOTE_COM = """User-agent: *
Disallow: /embed/*
Disallow: /intent/*
Disallow: /preview/*
Disallow: /api/*
Disallow: /pdf/*
Disallow: /wrap_up/*
Disallow: /search
Disallow: /login?*
Disallow: /signup?*
Disallow: /m/*/archive

# /:urlname/~
Disallow: /*/archives
Disallow: /*/archives/*
Disallow: /*/followers
Disallow: /*/followings
Disallow: /*/likes
Disallow: /*/magazines
Disallow: /*/menu/*
Disallow: /*/message
Disallow: /*/terms/specified

User-agent: Googlebot
User-agent: bingbot
User-agent: Yeti
Disallow: /*/message
Disallow: /embed/*
Disallow: /*/archives
Disallow: /*/archives/*
Disallow: /*/terms/specified
Disallow: /api/v2/boards/*/reserved_posts
Disallow: /api/v2/attachments
Disallow: /*/rss
Disallow: /intent/*
Disallow: /wrap_up/*
Disallow: /preview/*
Disallow: /search

Sitemap: https://note.com/sitemaps/production/note.com/sitemap.xml.gz
"""

ZENN_DEV = """User-agent: *
Disallow: /search

User-agent: Bytespider
Disallow: /

Sitemap: https://zenn.dev/sitemaps/_index.xml
"""

UA = "n0-agent (read-only; github.com/nemuprojectofficial-glitch/n0-public)"

CASES = [
    # (robots.txt, url, expected, why this case is here)
    (NOTE_COM, "https://note.com/api/v3/searchs?context=note&q=zorbilax", False,
     "the request session 110 actually sent. Disallow: /api/*"),
    (NOTE_COM, "https://note.com/search?q=%E8%B3%BC%E5%85%A5", False,
     "no wildcard; the old gate got this one right"),
    (NOTE_COM, "https://note.com/someone/archives", False,
     "Disallow: /*/archives — a wildcard in the middle"),
    (NOTE_COM, "https://note.com/someone/n/n0123456789ab", True,
     "an article page. Nothing forbids it, and the measurement needs it"),
    (NOTE_COM, "https://note.com/", True, "the root is not forbidden"),
    (NOTE_COM, "https://note.com/sitemaps/production/note.com/sitemap.xml.gz", True,
     "the sitemap the same file points at must stay reachable"),
    (ZENN_DEV, "https://zenn.dev/search?q=x", False, "zenn closes its search too"),
    (ZENN_DEV, "https://zenn.dev/someone/books/abc", True, "a book page is open"),
    (ZENN_DEV, "https://zenn.dev/", True, "the Bytespider group is not us"),

    # Group selection: a rule aimed at another crawler is not a rule aimed at us.
    ("User-agent: Googlebot\nDisallow: /\n", "https://x.test/a", True,
     "someone else's total ban does not apply to this tool"),
    ("User-agent: *\nDisallow: /\n\nUser-agent: n0-agent\nDisallow:\n",
     "https://x.test/a", True,
     "a group naming this tool wins over the catch-all, even when it is more permissive"),
    ("User-agent: *\nDisallow:\n", "https://x.test/a", True,
     "an empty Disallow is permission, not a zero-length prefix that blocks everything"),

    # Precedence, both directions.
    ("User-agent: *\nDisallow: /a/\nAllow: /a/b\n", "https://x.test/a/b", True,
     "longer match wins: the allow is more specific"),
    ("User-agent: *\nAllow: /a/\nDisallow: /a/b\n", "https://x.test/a/b", False,
     "and it wins in the other direction too"),
    ("User-agent: *\nAllow: /a\nDisallow: /a\n", "https://x.test/a", True,
     "equal length: allow wins the tie"),

    # The $ anchor.
    ("User-agent: *\nDisallow: /*.pdf$\n", "https://x.test/doc.pdf", False,
     "$ anchors the end"),
    ("User-agent: *\nDisallow: /*.pdf$\n", "https://x.test/doc.pdf?v=2", True,
     "and the query string means this is not the end"),

    # booth.pm, the host that started session 107's gate.
    ("User-agent: *\nDisallow: /terms\n", "https://booth.pm/terms", False,
     "session 63 fetched this path; session 107 found the rule"),
    ("User-agent: *\nDisallow: /terms\n", "https://booth.pm/", True,
     "and the root stayed open — a 403 is not a prohibition"),

    # Nothing at all.
    ("", "https://x.test/anything", True, "an empty robots.txt restricts nothing"),
]


def selftest():
    import urllib.robotparser

    bad = 0
    for text, url, expected, why in CASES:
        got = robots_allows(text, UA, url)
        ok = got == expected
        bad += not ok
        print("%s  %-5s %-52s  %s" % ("ok  " if ok else "FAIL", got, url, why))

    # The defect itself, pinned as a test. If a future Python implements
    # wildcards in robotparser, this line fails and the comment above becomes
    # history rather than a live reason for this file.
    old = urllib.robotparser.RobotFileParser()
    old.parse(NOTE_COM.splitlines())
    old_says = old.can_fetch(UA, "https://note.com/api/v3/searchs?q=x")
    print("%s  stdlib robotparser allows the disallowed /api/ path: %s"
          % ("ok  " if old_says else "FAIL", old_says))
    bad += not old_says

    # How much of one real file the old gate could apply at all. A pattern with
    # a `*` in it is enforceable by a literal-prefix parser only against a URL
    # that contains a literal asterisk, which no page on the host has.
    star = [p for allow, p in robots_rules_for(NOTE_COM, UA) if not allow and p]
    reachable = [p for p in star if "*" not in p]
    print("     note.com prints %d Disallow rules for this crawler; a literal-prefix"
          " parser can enforce %d of them (%s)"
          % (len(star), len(reachable), ", ".join(reachable)))

    print("\n%d case(s) failed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) == 3:
        # robots_rules.py <robots.txt file> <url>
        with open(sys.argv[1], encoding="utf-8") as fh:
            print(robots_allows(fh.read(), UA, sys.argv[2]))
        sys.exit(0)
    sys.exit(__doc__)
