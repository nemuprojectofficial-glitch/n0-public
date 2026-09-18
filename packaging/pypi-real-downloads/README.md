# How many of your PyPI downloads were people?

You published a package. The badge says a number. You want to know what the
number actually is.

```console
pip install pypi-real-downloads
real-downloads your-package-name
```

Or without installing anything:

```console
uvx --from pypi-real-downloads real-downloads your-package-name
```

No account, no API key, no signup. Standard library only — this package has
zero dependencies.

---

## What it prints

A real run against a real package. This is verbatim output, not an
illustration:

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

Three percent. That is the author's own other package, measured with this tool
and published rather than quietly left out.

Run `real-downloads --demo` to see the layout with no network at all, before
you point it at anything of yours.

---

## Where the number comes from

PyPI publishes its download log, and every row in it records **which installer
asked**. `pip` is in there. So is `bandersnatch`, which is a declared full
mirror that downloads everything ever published, forever, on a schedule. So is
the empty string, which is whatever sent no installer header at all.

The split is that column, grouped. There is no model, no heuristic, no
traffic-shape guessing. Every installer on the not-a-person side is printed
with the one-line reason it is there, so if you think a line is wrong you can
argue with that line instead of with the total.

The data is PyPI's own public download log, read through ClickHouse's free
demo endpoint. Nothing is written; no credential is sent.

---

## What the number does not mean

**"Could have been a person" is a ceiling, not a headcount.** CI runners drive
`pip`. Docker builds drive `pip`. Dependency bots drive `pip`. The installer
field cannot tell you which of those you are looking at, and this tool will not
pretend otherwise. What it replaces was the ceiling on the ceiling.

If your number comes back at 3%, the useful reading is not *"only 11 real
users"*. It is: **the headline was answering a different question than the one
you were asking it.**

**And some of the `pip` is you.** Every time you `pip install` your own package
to check that a release works, you add a `pip` row to your own numbers. On a
package with a handful of installs a day, your own release-day smoke test can be
most of the person-possible side. This is not hypothetical: on the day this
package was published it recorded 12 `pip` rows, and at least one was its author
verifying that `pip install` worked. Nothing in the dataset can tell yours apart
from a stranger's, so if the number matters to you, keep your own list of the
installs you ran.

---

## The silent zero in your package's name (fixed in 0.1.1)

PyPI's download log is keyed on the **PEP 503 normalized** name — lowercase,
with every run of `-`, `_` and `.` collapsed to one `-`. The name PyPI *shows*
you, on your own project page, is not that. Asked over the same window, from the
same endpoint, in the same minute on 2026-09-18:

| asked for | rows | downloads |
|---|---:|---:|
| `Django` | 0 | **0** |
| `django` | 48,344 | **23,925,705** |
| `scikit_learn` | 0 | **0** |
| `scikit-learn` | 10,518 | **107,528,449** |

HTTP 200 every time. No error, no warning — just zero.

**Version 0.1.0 of this package had that bug.** It passed your argument straight
into the query, so typing `Django` got you a confident zero and a sentence
explaining that PyPI's log had no rows for you yet — the exact failure the
section below exists to refuse, rebuilt one function lower. It survived because
every name the author had tested on was already lowercase with a hyphen.

0.1.1 normalizes first and prints the name it actually asked about whenever that
differs from what you typed. **If you query the dataset yourself, normalize
first** — `re.sub(r"[-_.]+", "-", name).lower()` — or you will get the same
zero, and nothing will tell you.

---

## Why it sometimes refuses to print

The endpoint this reads from will, under load, return the aggregate of a
**partially-read** scan with HTTP 200 and no warning. A truncated read can only
lose rows, so its wrong answer is always *smaller* than the truth — which means
it always points at "nobody downloaded this", which is the exact conclusion you
came here to check.

So before printing anything about your package, it asks about a package that
cannot possibly be small, and if the answer about *that* comes back small, it
prints nothing and exits non-zero:

```
  Not printing a number.

  The check that runs before every measurement did not pass:
    requests returned nothing. Either the endpoint is not answering
    or the dataset moved; no number below is a measurement.
```

A number from a failing instrument is not a small number. It is an unknown one.
The mechanism, with a reproduction and the one URL parameter that turns the
silence into an error, is written up in
[A-ZERO-THAT-MEANS-UNKNOWN.md](https://github.com/nemuprojectofficial-glitch/n0-public/blob/main/A-ZERO-THAT-MEANS-UNKNOWN.md).

---

## Two things it will not do

**It will not tell you the number is fine.** There is no grade, no score, no
"healthy range". It prints the split and the reasons and stops.

**It will not ask you for anything.** No signup, no star, no telemetry, no
reply. You run it, you get your number, and that is the end of the
transaction.

---

## Related

- **[`ARE-PYPI-DOWNLOAD-COUNTS-REAL.md`](https://github.com/nemuprojectofficial-glitch/n0-public/blob/main/ARE-PYPI-DOWNLOAD-COUNTS-REAL.md)**
  — the same question at population scale instead of for your package, and what
  a brand-new package's first days actually look like.
- **`reach_probe.py`**, shipped inside this package, is the measurement itself:
  `python3 -m reach_probe --selftest` runs its counterexample suite, and the
  installer classification lists are in the open at the top of the file.

## License

MIT.
