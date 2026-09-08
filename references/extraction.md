# Getting text out of the PDF

## First: which kind of PDF is this

```bash
pdftotext -layout statement.pdf - | head -40
```

- **Text comes out**: there is a text layer. Use it. This is the good case and covers
  most statements downloaded from online banking.
- **Nothing, or a handful of stray characters**: the pages are images. It is a scan, or a
  bank that renders statements as pictures. You need OCR before anything else.

`statement.py detect` says the same thing more bluntly: no dates at all in the extracted
text means there was no text to extract.

## Why `-layout` and not plain extraction

A bank statement is a table drawn with absolutely positioned text. Plain extraction
returns the characters in the order the PDF stores them, which is frequently not reading
order: amounts arrive detached from their rows, columns interleave, and no regex saves
you afterwards.

`-layout` reconstructs the visual arrangement with spaces, which turns each transaction
back into one line with its columns separated by runs of whitespace. Everything in
`statement.py parse` assumes that shape.

## When it is a scan

OCR quality decides everything downstream, and the two failure modes are specific:

- **Digits.** `5` and `6`, `1` and `7`, `0` and `8` are the classic confusions, and a
  single wrong digit in an amount produces a statement that looks perfect and is wrong.
  This is exactly what the balance chain catches.
- **Decimal separators.** A comma read as a full stop turns 1.234,56 into 1.234.56 and
  then into nonsense. Force the decimal convention with `--decimal-comma` or
  `--decimal-dot` rather than letting detection guess on noisy text.

Whatever OCR you use, **never** accept the output without running `verify`. On a scan the
chain is not a nicety, it is the only thing standing between you and a plausible wrong
number.

## Column detection, when the layout is not enough

Some statements put the debit and credit in two separate columns rather than one signed
amount. Two signals distinguish them:

- Every row has a value in exactly one of the two columns.
- The column positions are stable across rows, within a couple of characters.

Take the horizontal position of each number and cluster the positions across the whole
document. Columns are the clusters; a number's column is decided by where it sits, not by
its order on the line. Then debit becomes negative and credit positive, and you are back
to one signed amount.

Do this at the document level, never per row. A row whose description happens to contain
a number will otherwise shift every column after it.

## Multi-line descriptions

A transaction routinely spans two or three lines. The continuation lines carry no date
and no amount.

Rule: **a line with a date and an amount starts a new transaction; a line with neither is
a continuation of the previous one.** Anything else is a header, a footer, a page break or
a repeated column title.

A parser that treats every line as a row produces a file with three times the rows and a
third of the money, and the balance chain will tell you immediately.

## Statements that cross a year boundary

A December-to-January statement has rows that omit the year, and inheriting the year of
the statement date puts the December rows in the wrong year.

Rule: read the statement period from the header, then assign the year by watching for the
month going backwards. A row whose month is smaller than the previous row's month has
crossed into the next year.

`--year` sets the base year when nothing in the rows carries one.

## Italian statements specifically

| Term | Meaning |
|---|---|
| Data contabile | Booking date, when the bank recorded it |
| Data valuta | Value date, when it counts for interest. Often days apart from the booking date |
| Dare / Avere | Debit / Credit, in the two-column layout |
| Saldo iniziale / finale | Opening / closing balance |
| Riporto | Carried forward, a page-break artefact and never a transaction |

Use the **booking date** for accounting and reconciliation. The value date matters for
interest calculations and almost nothing else, but keep it: you cannot recover it later.
