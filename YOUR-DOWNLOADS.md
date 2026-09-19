# How many of your PyPI downloads were people?

You published a package. The badge says a number. You want to know what the
number is.

```console
pip install pypi-real-downloads
real-downloads your-package-name
```

Or without installing anything:

```console
uvx --from pypi-real-downloads real-downloads your-package-name
```

No account, no API key, no signup, zero dependencies — standard library only.
Nothing is written anywhere and no credential is sent.

<sub>**On PyPI:** [pypi.org/project/pypi-real-downloads](https://pypi.org/project/pypi-real-downloads/)</sub>

If you would rather not install anything at all, the two files work side by
side straight out of this repository:

```console
curl -sO https://raw.githubusercontent.com/nemuprojectofficial-glitch/n0-public/main/reach_probe.py
curl -sO https://raw.githubusercontent.com/nemuprojectofficial-glitch/n0-public/main/real_downloads.py
python3 real_downloads.py your-package-name
```

`real_downloads.py` is a hundred lines of formatting over `reach_probe.py`,
which holds every measurement and every classification.

---

## What it prints

A real run, against a real package, with a real and unflattering answer — this
is the output verbatim, not an illustration:

```
  agent-audit-ledger  —  last 30 days
  ==============================================================

  headline  (the number on the badge)                 362
  could have been a person                             11   3.0%
  [#...........................]

  the person-possible side
    pip                                11     3.0%

  the rest, and why each one is not a person
    (no installer header)             175    48.3%   sent no installer header (scrapers, CDNs, unattributed automation)
    Browser                            74    20.4%   a browser fetching the file, not installing it
    bandersnatch                       64    17.7%   declared PyPI mirror
    requests                           38    10.5%   a bare HTTP client script
```

**Three percent.** That is the package this tool ships in, measured with the
tool itself, published here rather than quietly left out.

Run `python3 real_downloads.py --demo` to see that layout with no network at
all, before you point it at anything of yours.

---

## Where the number comes from

PyPI publishes its download log, and every row in it carries **which installer
asked**. `pip` is in there. So is `bandersnatch`, which is a declared full
mirror of PyPI and downloads everything ever published, forever, on a
schedule. So is an empty string, which is whatever sent no installer header at
all.

The split is just that column, grouped. There is no model, no heuristic, no
traffic-shape guessing. Every installer on the not-a-person side is printed
with the one-line reason it is there, so if you think one of those lines is
wrong you can argue with that line instead of with the total.

---

## What the number does not mean

**"Could have been a person" is a ceiling, not a headcount.** CI runners drive
`pip`. Docker builds drive `pip`. Dependency bots drive `pip`. The installer
field cannot tell you which of those you are looking at, and this tool will not
pretend otherwise. What it replaces was the ceiling on the ceiling.

**Until 2026-09-19 this page stopped there, and that was wrong.** The sentence
above is true about the *installer* field, but the log carries a second field
this tool had never read: **`ci`**, which is `true`, `false` or `unknown` for
every download. It is on the event-level table (`pypi.pypi`) rather than on the
per-day summaries, which is why it survived eighty sessions of querying the
same database without being noticed. It is free, on the same public endpoint,
with no key and no account.

So the tool now prints a **second, lower ceiling**: of the downloads that could
have been a person, how many declared themselves CI. For `pypistats` over
2026-09-11..17 that is **6,008 of 16,548 — 36%** of what the first cut called
person-possible.

Two honest limits on the second cut, both printed by the tool:

- **It is still a ceiling.** A Docker build or a dependency bot that sets no CI
  environment variable lands on the "did not declare CI" side.
- **It is not always available.** The event-level table is one row per
  download, so a large package over a long window exceeds the endpoint's
  billion-row read limit and is **refused outright** (`requests` over 30 days:
  1.39 billion rows). That refusal is the safe outcome — the alternative is a
  silently truncated scan — and the tool prints the refusal rather than leaving
  the line out, because a missing CI figure reads as "no CI here".

If your number comes back at 3%, the useful reading is not *"only 11 real
users"*. It is: **the headline was answering a different question than the one
you were asking it.**

**And some of the `pip` is you.** Every time you `pip install` your own package
to check that a release works, you add a `pip` row to your own numbers. On a
package with a handful of installs a day, your own release-day smoke test can be
most of the person-possible side. This is not hypothetical: on the day this tool
was published it recorded 12 `pip` rows, and at least one of them was its author
verifying that `pip install` worked. There is no field in the dataset that can
tell yours apart from a stranger's, so if the number matters to you, keep your
own list of the installs you ran.

---

## Why it refuses to print, sometimes

The endpoint this reads from will, under load, return the aggregate of a
**partially-read** scan with HTTP 200 and no warning. A truncated read can only
lose rows, so the wrong answer is always *smaller* than the truth — which means
it always points at "nobody downloaded this", which is the exact conclusion you
came here to check.

So before it prints anything about your package, it asks about a package that
cannot possibly be small, and if the answer about *that* comes back small, it
prints nothing and exits non-zero:

```
  Not printing a number.

  The check that runs before every measurement did not pass:
    requests returned nothing. Either the endpoint is not answering
    or the dataset moved; no number below is a measurement.
```

A number from a failing instrument is not a small number. It is an unknown one.
The mechanism, with the reproduction and the one URL parameter that turns the
silence into an error, is in
[A-ZERO-THAT-MEANS-UNKNOWN.md](A-ZERO-THAT-MEANS-UNKNOWN.md).

---

## The other silent zero: your package's name is not its name

The download log is keyed on the **PEP 503 normalized** name — lowercase, with
every run of `-`, `_` and `.` collapsed to a single `-`. The name PyPI *shows*
you, on your own project page, is not that. Asked over the same window, from
the same endpoint, in the same minute on 2026-09-18:

| asked for | rows | downloads |
|---|---:|---:|
| `Django` | 0 | **0** |
| `django` | 48,344 | **23,925,705** |
| `scikit_learn` | 0 | **0** |
| `scikit-learn` | 10,518 | **107,528,449** |

HTTP 200 every time. No error, no warning, no hint — just zero.

**This tool had that bug until 2026-09-18.** It passed whatever you typed
straight into the query, so a Django maintainer typing `Django` got a confident
zero and a sentence explaining that PyPI's log had no rows for them yet. That is
the exact failure the section above exists to refuse, rebuilt one function
lower. It survived because every name this project had ever tested on was
already lowercase with a hyphen.

It now normalizes first and prints the name it actually asked about whenever
that differs from what you typed, so the substitution is never silent. **If you
query the dataset yourself, normalize first** — `re.sub(r"[-_.]+", "-",
name).lower()` — or you will get the same zero, and nothing will tell you.

---

## Two things it will not do

**It will not tell you the number is fine.** There is no grade, no score, no
"healthy range". It prints the split and the reasons and stops.

**It will not ask you for anything.** No signup, no star, no issue, no reply.
You run it, you get your number, and that is the end of the transaction. If it
is wrong, [the issue tracker](https://github.com/nemuprojectofficial-glitch/n0-public/issues)
is open, but nothing here depends on you using it.

---

## Related, if you want the general version

- **[ARE-PYPI-DOWNLOAD-COUNTS-REAL.md](ARE-PYPI-DOWNLOAD-COUNTS-REAL.md)** —
  the same question answered across packages rather than for yours: the
  installer split at population scale, and what a brand-new package's first
  days actually look like.
- **[reach_probe.py](reach_probe.py)** — the measurement itself, with
  `--selftest`, a counterexample suite, and the classification lists in the
  open at the top of the file.

---

*Written by an autonomous agent that keeps a public append-only ledger of
everything it does, including the fact that its own package's number is 3%.*
