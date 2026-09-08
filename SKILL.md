---
name: bank-statement-to-table
description: Use when turning a bank statement into a spreadsheet or a ledger - extracting transactions from a PDF or scan, parsing dates and amounts across European and Anglo conventions, handling multi-line descriptions and page breaks, and above all proving the extraction is correct by checking it against the statement's own running balance before anyone acts on the numbers.
---

# Bank Statement to Table

## Overview

Extraction is the easy half. Any parser produces a table; the question is whether the
table is the statement. A bank statement carries its own proof, so you never have to
guess:

```
balance[i] == balance[i-1] + amount[i]      every row
opening + sum(amounts) == closing           the whole statement
```

**Core principle: never hand over an extraction that has not passed both checks.**
Extraction is guessing. Verification is knowing.

## When to use

- A PDF or scanned bank statement that needs to become a spreadsheet or accounting import
- Dates and amounts in a mixed or unclear convention
- An extraction that "looks right" and needs to be proven before it is used
- Multi-line descriptions, page breaks, repeated headers, carried-forward lines
- A statement that crosses a year boundary with rows that omit the year

**Not for:** categorising transactions, budgeting, or reading a statement to answer a
question. This is about getting the numbers out correctly.

## The three commands

```bash
pdftotext -layout statement.pdf - > statement.txt

python3 scripts/statement.py detect statement.txt
python3 scripts/statement.py parse  statement.txt --out rows.csv
python3 scripts/statement.py verify rows.csv --opening 1240.55 --closing 2103.11
```

```
VERIFIED: the parse reproduces the statement exactly.
```

That line, and only that line, means the file is usable.

## Two decisions made once per document, never per row

**Date order.** `01/06` is ambiguous and no cleverness resolves a single row. Resolve it
for the whole file: if any date anywhere has a first component above 12, the document is
day-first. Deciding per row produces a statement where January and October are silently
swapped.

**Decimal separator.** `1.234,56` and `1,234.56` are the same number from two different
worlds. Decide once, from the whole text. Deciding per value turns `1.234` into either
1234 or 1.234 depending on the row, and the totals then miss by three orders of magnitude
on exactly the rows where it matters.

`detect` reports both before you commit to them; `--day-first`, `--month-first`,
`--decimal-comma` and `--decimal-dot` override them.

## The postal-code rule, applied to money

Amounts are parsed, not eyeballed, and the parser has to handle all of these as the same
concept:

`1.234,56` · `1,234.56` · `1'234.56` · `-82,40` · `82,40-` · `(82,40)` · `82.40 DR` · `82.40 CR`

Trailing minus, parentheses and DR suffixes all mean negative, and a statement will use
whichever one its printing system preferred.

## Line classification

**A line with a date and an amount starts a transaction. A line with neither continues
the previous description. Everything else is a header, a footer or a page break.**

Descriptions routinely run to three lines. A parser that treats every line as a row
produces a file with three times the rows and a third of the money, and the chain check
catches it immediately.

## When verification fails, the difference tells you what happened

| The difference | What it means |
|---|---|
| Equals an amount on a visible row | That row is duplicated or missing |
| Exactly twice an amount on a row | That row was read with the wrong sign |
| Round and large | A thousands separator was read as a decimal point |
| Off by a factor of 100 | Wrong decimal convention for this document |
| No single row explains it | A missing page, or the balance column read as the amount |

`verify` prints these hints on the row it names.

## Reference

| Topic | File |
|---|---|
| Text layer vs scan, why `-layout`, column clustering, year boundaries, Italian terms | `references/extraction.md` |
| The two checks, difference signatures, tolerance, what to record, privacy | `references/verification.md` |

## This is a private document

A statement carries the account holder, the IBAN, the balance and a complete map of a
person's life by counterparty. Everything here runs locally and makes no network call, on
purpose. Do not paste statement contents into a chat, a shared drive or a log, and delete
the intermediate text dumps when you are done.

## Common mistakes

- **Shipping an extraction that was never verified.** The whole point.
- **Widening the tolerance until the file passes.** A tolerance loose enough to hide a
  rounding difference is loose enough to hide a wrong digit.
- **Deciding the date order or decimal convention per row.**
- **Using plain `pdftotext` without `-layout`.** The characters come out in storage order,
  not reading order, and no regex recovers from that.
- **Inheriting the statement's year on a December-to-January file.**
- **Using the value date for accounting.** Booking date for the ledger; keep the value
  date, because you cannot recover it later.
