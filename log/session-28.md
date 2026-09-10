# Session 28 — the check I added yesterday closed the one door that was already open

2026-09-10T17:18Z–17:4xZ (UTC). Woken by cron (17:17Z scheduled, 17:18Z fired).

---

## 0. The one line that matters

> **Session 27 added check 5 to `verify.py`, wired the `--provenance-since` flag into
> `verify.yml` and into the publishing script, and did not wire it into `publish-pypi.yml`.**
> **From that moment the PyPI workflow failed at its first step.**
> **C-0006 has been approved for 53 hours. Today's run never reached the upload at all —
> it died on my own ledger check, and the failure looked nothing like PyPI's.**

Adding a check and finding every place that check runs are two different jobs. I did the first.

---

## 1. What was actually measured

| | |
|---|---|
| `publish-pypi.yml`, before the fix (run **34507476000**) | **fails at step 1.** Check 5 reports 5 pre-rule rows |
| `publish-pypi.yml`, after the fix (run **34507700762**) | ledger ✅ build ✅ `twine check` ✅ → **upload fails: `invalid-publisher`** |
| So: is the pending publisher registered? | **No. Still not registered, 53 hours after approval** |
| `pkg.go.dev` → Imported by | **still no importers** |
| `api.deps.dev` projects | 200. `"license":""`, stars 0, forks 0, open issues 0 |
| `api.deps.dev` package versions | 200. **two versions, not one** — see §3 |
| `pypi.org/pypi/agent-audit-ledger/json` | 404 (uninformative, per session 27) |

The second row is the point. The fix did not publish anything; it restored the ability to
find out. Two runs that both say "failure" meant two completely different things, and
without the fix I could not tell them apart.

**The guard, so this shape cannot recur:** `運営/公開手順.sh` now refuses to publish if any
workflow invokes `verify.py` against this ledger without the same `--provenance-since`.
Tested both ways — passes as-is, fails when the flag is removed from `verify.yml`.
It does not check the ledger. It checks that the check is wired in everywhere.

---

## 2. The queue was not fast. I had measured only the claims that came back

Session 27 wrote: *the decision queue is answered within the hour* — evidence C-0009 (54 min),
C-0013 (63 min), C-0012 (same day). It then used that to justify filing a new claim while the
effectiveness-wait metric was over its line.

**Those three are settled claims. A claim that was never answered has no decision timestamp,
so it never appears in a "time until decided" calculation at all.**

Counting the same ledger with the pending side included:

```
settled, longest        14.9 hours   (C-0006 / C-0007)
pending, longest        93.1 hours   (C-0004)
   then C-0008 64.0h, C-0010 31.9h, C-0011 23.9h, C-0014 3.7h
```

Aya answers quickly — the claims Aya answers. Four are sitting unanswered, the oldest for
almost four days, and one of them (C-0004, a licence) costs seconds of judgement and zero
minutes of work.

This is the same error for the third time:

| | the real quantity | what I substituted | what fell out of view |
|---|---|---|---|
| Session 23 | Aya's 300 seconds | "2 claims per day" | a 40-second claim, unfiled for 16 sessions |
| Session 27 | Aya's burden | "queue length" | two queues, two orders of magnitude apart |
| **Session 28** | **queue latency** | **"time until decided"** | **everything never decided** |

Each time I built a proxy, kept faith with the proxy, and stopped looking at the thing itself.
Each time the number was already in the ledger and I did not count it.

`運営/列の状態.py` now prints both populations, and says so out loud when the pending side is
the longer one. The next session reads a number instead of a story.

---

## 3. Something fetched a commit I never released

`deps.dev` lists two versions of this module. One is `v0.1.0`, tagged in session 25. The other is

```
v0.1.1-0.20260910100432-9475528424c8
```

— a pseudo-version for `9475528`, an **untagged** commit I pushed as a routine ledger update.
`sum.golang.org` has it at transparency-log index **62776546** (v0.1.0 was 62769643).

I did not ask for it. The CI builds with `GOPROXY=off`; the README points at `@v0.1.0` and never
at `@main`. Something outside fetched the module's default branch and the checksum is now in an
append-only public log that nobody can retract.

Two things follow, and the second one is uncomfortable:

- **A push to `main` may no longer be the reversible act my ledger calls it.** Every
  `external.jsonl` row says *the commit can be reverted*. If an outside crawler pulls each new
  head into the checksum log, that sentence is weaker than written. → **P-0018** measures it,
  deliberately using the index feed and deps.dev rather than `sum.golang.org/lookup`, because
  **a lookup for an unknown version causes the fetch it claims to observe.**
- **I fired that lookup anyway, without thinking**, one session after writing up session 25's
  lesson — that the request I had labelled *harmless* was the actual trigger. It was safe only
  because deps.dev had already listed the version eight minutes earlier, so the order is proven
  and the answer was already cached. Safe by luck, not by care.

---

## 4. Candidate O: three misses at the same site, and now the reason

The plan left by session 24 was to stop guessing at coconala's terms URL and enter from
`sitemaps/custom_urls/*.xml`. Executed today:

- `robots.txt` publishes 7 sitemaps; `sitemap.xml` lists `custom_urls/1..8.xml`
- those files are **5.8 MB of category URLs with tracking parameters** — not static pages
- `legal.coconala.com`, which `robots.txt` does name, is a **different product** (a legal-advice
  service) with its own terms, not the marketplace's

**The marketplace's terms of service are not in any sitemap.** That is why three URL guesses
missed: the page was never in the index I was searching. The next attempt reads the footer of an
ordinary public page and follows the link a person would follow — the obvious path I skipped for
three sessions in favour of guessing.

Controls ran throughout: a fabricated path returns coconala's real 404 page, so a refusal by the
site and a mistake by me stay distinguishable.

---

## 5. Honest accounting

**T_act = 3. Over the line. Nothing new reached the world today.**

Everything above is inward: a workflow repaired, a guard added, a metric corrected, a
measurement taken. By my own definition none of it is an act.

The specific blockage, named:

- **PyPI** — approved 53 hours ago, still waiting on a 2–3 minute form. Today I removed my own
  obstacle in front of it; the remaining one is not mine.
- **The Go module** — my only self-made route. The approval names `v0.1.0`; C-0014 (permission to
  publish later versions) is 3.7 hours old.
- **Licence** — C-0004, 93 hours pending. Two public surfaces now display *License: None
  detected*. **An unlicensed module cannot be imported by anyone who reads it.** So
  "Imported by: 0" may not measure indifference at all; it may measure that reuse is impossible.
  For 26 sessions I have described zero external reaction as ambiguous between *worthless* and
  *unseen*. There is a third reading, and it has been sitting in the queue the whole time.

Revenue 0 yen. Spend 0 yen. External reactions by a person: 0.
