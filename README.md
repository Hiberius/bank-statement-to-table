# Bank Statement to Table

**An Agent Skill that turns a bank statement into a spreadsheet and then proves the
result is correct, using the statement's own running balance. European and Anglo number
formats, multi-line descriptions, page breaks, scans. Entirely offline.**

[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)
![Zero dependencies](https://img.shields.io/badge/dependencies-0-6E56CF)
![Offline](https://img.shields.io/badge/network-never-8f9bb8)

```bash
npx skills add Hiberius/bank-statement-to-table
```

---

## Anyone can extract. The question is whether it is right

```bash
pdftotext -layout statement.pdf - > statement.txt
python3 scripts/statement.py parse  statement.txt --out rows.csv
python3 scripts/statement.py verify rows.csv --opening 1240.55 --closing 2103.11
```

```
rows                7 (7 carry a balance)
chain checks        6
chain breaks        0
sum of movements    862.56
opening + movements 2103.11
stated closing      2103.11
difference          0.00

VERIFIED: the parse reproduces the statement exactly.
```

Every running balance must equal the previous balance plus the movement. That is not a
convention, it is what a balance is. So the parse either reproduces the chain from the
opening balance to the closing balance, or it is wrong and the chain says which row.

Change one digit and:

```
NOT VERIFIED: the parse does not reproduce the statement.

  break at row 1, 2026-06-03  PAGAMENTO POS SUPERMERCATO
    2740.55 -8.24 should give 2732.31, the statement says 2658.15 (off by -74.16)
    hint: the difference equals the amount on 2026-06-05: that row is probably
          duplicated or missing
```

## Two decisions made once, never per row

`01/06` is ambiguous and no cleverness resolves a single row: if any date in the file has
a first component above 12, the whole document is day-first. Deciding per row silently
swaps January and October.

`1.234,56` and `1,234.56` are the same number from two different worlds. Deciding per
value turns `1.234` into 1234 on one row and 1.234 on the next, and the totals then miss
by three orders of magnitude.

```bash
python3 scripts/statement.py detect statement.txt
```
```
date order             day-first (dd/mm)
decimal separator      comma (1.234,56)
```

## It handles what real statements do

- **Multi-line descriptions.** A line with a date and an amount starts a transaction; a
  line with neither continues the previous one. Nothing else is a row.
- **Page breaks, repeated column headers, carried-forward lines, opening and closing
  balance lines.** All skipped, and counted so you can see they were.
- **Every negative convention**: `-82,40`, `82,40-`, `(82,40)`, `82.40 DR`.
- **Value date separate from booking date**, kept, because you cannot recover it later.
- **Scans.** `detect` tells you there is no text layer instead of returning an empty table.

## Documentation

- [`SKILL.md`](SKILL.md) — the skill itself, what the agent reads
- [`references/extraction.md`](references/extraction.md) — text layer vs scan, why `-layout`, column clustering for debit/credit layouts, year boundaries, Italian statement vocabulary
- [`references/verification.md`](references/verification.md) — the two checks, difference signatures, tolerance, what to record for an accountant, privacy

## Your statement never leaves your machine

No network calls, no telemetry, no dependencies, by design. A statement carries the
account holder, the IBAN, the balance and a complete map of a person's life by
counterparty.

## License

MIT.
