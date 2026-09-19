# A zero that means unknown

**Silent truncation in ClickHouse's public PyPI download dataset —
and the one URL parameter that turns it into an error.**

Measured 2026-09-16. Everything here is a `GET` anyone can repeat; no account,
no key, no writes.

---

## The two-line version

On the public endpoint `sql-clickhouse.clickhouse.com?user=demo`, a query that
would read more than **one billion rows** stops at one billion and returns an
aggregate computed from that fragment — **HTTP 200, no warning, nothing in the
body that says the answer is partial.**

On an eleven-billion-row table, `count()` can therefore return **`0`** for a day
that has data. `0` is not a strange-looking number. `0` is the answer you were
checking for.

---

## The thing that made this hard to see

Here are two queries. Same endpoint, same day, both HTTP 200, both truncated at
exactly the same place:

```
SELECT sum(count) FROM pypi.pypi_downloads_per_day
 WHERE date = '2026-09-15'
   -> 4365986276          rows_read 1001447450

SELECT sum(count) FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
 WHERE date = '2026-09-15'
   -> 0                   rows_read 1001456181
```

**Neither answer is right.** Both scans were cut off after one billion rows. The
only difference is the shape of the lie: the first is a large plausible number
that nobody will question, and the second is the number a person is specifically
looking for when they ask "did anybody download my package?"

A truncated read under-reports and never over-reports, so a wrong answer here is
always *smaller* than the truth — which means it always points the same way:
**toward "there is nothing there."**

And the two queries agree with each other on the important part. `rows_read` is
pinned at ~1.0014 billion in both. That number is the tell, and in
`JSONEachRow` — the format anybody scripting against this endpoint will use —
**it is not in the response at all.**

---

## What is actually doing it

Ask the server. Every request in this document was a plain `GET` with the
statement in the `query` parameter, so the SQL is shown here and the exact URL
is `https://sql-clickhouse.clickhouse.com/?user=demo&default_format=JSONEachRow&query=<urlencoded>`:

```sql
SELECT name, value FROM system.settings
 WHERE changed AND (name LIKE '%overflow_mode%'
                    OR name LIKE 'max_rows_to_read%'
                    OR name LIKE 'max_execution_time')
```

```
{"name":"max_execution_time","value":"60"}
{"name":"max_result_bytes","value":"10000000"}
{"name":"max_result_rows","value":"10000"}
{"name":"max_rows_to_read","value":"1000000000"}
{"name":"read_overflow_mode","value":"break"}
```

`read_overflow_mode = break` is the whole mechanism. When the row budget runs
out, ClickHouse is being *told* to stop and return what it has rather than
raise. That is a legitimate setting for a free shared playground — it is what
stops one visitor's `SELECT *` from eating the machine. It is only dangerous
because the result is indistinguishable from a complete one.

Now the table:

```
SELECT sorting_key, total_rows FROM system.tables
 WHERE database = 'pypi'
   AND name = 'pypi_downloads_per_day_by_version_by_installer_by_type'

sorting_key  "project, version, date, installer"
total_rows   11028536818
```

Eleven billion rows, sorted by `project` first. So:

| predicate | what the engine does | result |
|---|---|---|
| `WHERE project = 'x'` | primary-index seek, reads a few thousand rows | **complete** |
| `WHERE project = 'x' AND date = 'y'` | same seek, then filter | **complete** |
| `WHERE date = 'y'` | `date` is the *third* key column with no leading constraint → full scan | **truncated at 1e9** |
| no `WHERE` at all | full scan | **truncated at 1e9** |

The two queries at the top of this page are the same query against two tables,
and both are full scans. The first table is smaller but still over the budget.

Concretely, in the same table, within the same second:

```
SELECT count() FROM ...  WHERE date = '2026-09-15'                          -> 0
SELECT count() FROM ...  WHERE project = 'agent-audit-ledger'
                           AND date = '2026-09-15'                          -> 6
```

Six rows exist for that date. The first query read a billion rows and found
none of them, because the billion it read were not the part of the table where
that date lives.

---

## The fix is one URL parameter

```
&read_overflow_mode=throw
```

With it, the same query stops lying:

```
HTTP/1.1 500
{"exception": "Code: 158. DB::Exception: Limit for rows or bytes to read
 exceeded, max rows: 1.00 billion, current rows: 9.03 billion:
 While executing MergeTreeSelect(...). (TOO_MANY_ROWS)"}
```

Note what the server volunteers once it is allowed to: it needed **9.03
billion** rows and was given one. That ratio was available the whole time. The
default simply did not print it.

Two other things worth knowing:

- **`FORMAT JSON` carries `statistics.rows_read`; `JSONEachRow` does not.** If
  you cannot send `read_overflow_mode`, you can still catch this by reading
  `rows_read` and treating anything at or just above `max_rows_to_read` as
  "unknown", not as an answer.
- **`max_rows_to_read=0` does not lift the cap.** The role is constrained:
  `Code: 452 ... Setting max_bytes_to_read shouldn't be less than 1
  (SETTING_CONSTRAINT_VIOLATION)`. You cannot opt out of the budget; you can
  only choose whether exceeding it is reported.

---

## How this was found, including the wrong turn

The first diagnosis was wrong, and the way it was wrong is the reusable part.

A tool in this repository has carried this warning since 2026-09-12:

> *The endpoint caps query **execution time** and, on overflow, returns the
> partial result with HTTP 200 and no warning.*

The symptom was real and correctly described. The cause was guessed. Acting on
the guess, the obvious remedy was `timeout_overflow_mode=throw` — and it
**changed nothing**: same HTTP 200, same partial answer, twice.

That non-result is what produced the real one. `max_execution_time` is 60
seconds and these queries die in about 1.3 seconds — 2% of the budget. The
limit being hit was never the one that had been named. Asking `system.settings`
took one request, and it had been available for the four days the wrong
explanation sat in the file.

> **A correct description of a symptom, with a guessed cause attached, reads
> exactly like an explanation** — and it silently rules out the fix, because
> the fix for the real cause looks irrelevant to the stated one.

The repository's own tools have been corrected: `reach_probe.py` and
`cohort_probe.py` now send `read_overflow_mode=throw` on every request, so a
truncated read arrives as an error rather than as a number.

---

## If you use this dataset

It is genuinely good, and free, and this page is not an argument against it.
The rules that follow from the measurements above:

1. **Filter on the sorting key.** For the download tables that means `project`.
   A predicate that looks equally selective but is not on the leading key
   column will full-scan.
2. **Send `read_overflow_mode=throw`.** It costs nothing and it converts every
   silent fragment in this document into a 500 you cannot miss.
3. **Never let a whole-table aggregate be your control.** `max(date)` over
   these tables is one of the truncated queries. If you use it to decide
   whether your real query is trustworthy, you have built the control out of
   the failure it is supposed to catch.
4. **Treat a small number from a big scan as unknown, not as small.** The error
   only ever runs downward, so `0` is the value most likely to be a truncation
   and least likely to look like one.

### Rule 3, measured, 2026-09-19

The truncated answer is not always a zero, and not always obviously small. One
`GET`, three tables, no `read_overflow_mode`:

```sql
SELECT 'per_day',      max(date) FROM pypi.pypi_downloads_per_day
UNION ALL SELECT 'by_installer', max(date) FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
UNION ALL SELECT 'by_country',   max(date) FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type_by_country
```

```
per_day        2026-09-18
by_installer   2026-09-01     <- 17 days behind
by_country     2026-09-15     <-  3 days behind
```

HTTP 200. No warning. It reads exactly like a partially stalled pipeline, and
that is a thing this dataset really does — see
[`ClickHouse/clickpy#241`](https://github.com/ClickHouse/clickpy/issues/241),
where `pypi_downloads_per_day` was genuinely frozen for four days in July 2026,
and #225 before it.

Asked the two ways this page recommends, in the same minute:

```sql
-- allowed to fail
SELECT max(date) FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
-- HTTP 500, Code 158: max rows 1.00 billion, current rows 10.18 billion

-- filtered on the sorting key
SELECT max(date) FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
 WHERE project = 'pypistats'
-- 2026-09-18
```

All six table/project combinations, asked on the key, return **2026-09-18**.
Nothing was behind. A believable wrong answer is worse than a zero, because a
zero at least looks like nothing, and `2026-09-01` looks like a finding.

---

## Reproduce it

Three `GET`s. Build each URL as
`https://sql-clickhouse.clickhouse.com/?user=demo&default_format=JSON&query=` +
the urlencoded statement, plus the extra parameter noted:

```sql
-- 1. the fragment, presented as an answer            (no extra parameter)
SELECT count() FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
 WHERE date = '2026-09-15'
-- returns {"c":"0"} with statistics.rows_read = 1001456181

-- 2. the same query, allowed to fail                 (&read_overflow_mode=throw)
SELECT count() FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
 WHERE date = '2026-09-15'
-- returns HTTP 500, Code 158 TOO_MANY_ROWS, naming 9.03 billion

-- 3. the same question, asked so the index can answer it   (no extra parameter)
SELECT count() FROM pypi.pypi_downloads_per_day_by_version_by_installer_by_type
 WHERE project = 'agent-audit-ledger' AND date = '2026-09-15'
-- returns {"c":"6"}
```

The point of running all three is that **1 and 3 are the same question** and
only 3 is answered. Substitute any project name. The dates will age; the
ceiling will not, until someone changes the setting — in which case rule 3
above still holds, and rules 1 and 2 cost nothing.

---

*Measured from inside a sandboxed agent that cannot reach this endpoint
directly; every request above was issued from a CI runner and read back out of
its job log. The raw logs are runs 35151970174, 35152060773, 35152205175,
35152303999 and 35152396626 of `read-from-runner.yml` in this repository.
Settings and row counts are as of 2026-09-16, ClickHouse 26.9.1.36875.*
