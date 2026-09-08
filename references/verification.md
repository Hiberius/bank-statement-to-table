# Verification

## The statement carries its own proof

Every running balance equals the previous balance plus the movement. That is not a
convention, it is what a balance is. So a parse either reproduces the chain from the
opening balance to the closing balance, or it is wrong somewhere and the chain says
where.

```
balance[i] == balance[i-1] + amount[i]          for every row
opening + sum(amounts) == closing               for the statement
```

**Never hand over an extraction that has not passed both.** Extraction is guessing;
verification is knowing.

## Two checks, because they catch different things

**The chain** localises an error to a row. One misread digit and it fires on exactly that
transaction.

**The total** catches what the chain cannot: a whole missing page. If page three is
absent and the chain resumes consistently on page four, every row-to-row check passes and
only the opening-to-closing total reveals the gap.

Run both. `statement.py verify --opening X --closing Y` does.

## Reading a difference

The difference has a signature, and each one has a different fix.

| Signature | What it means |
|---|---|
| Equals an amount you can see on a row | That row is duplicated, or it is missing |
| Exactly twice an amount on a row | That row was read with the wrong sign |
| Round and large (1000, 10000) | A thousands separator was read as a decimal point |
| Off by a factor of 100 | The decimal separator convention is wrong for the document |
| No single row explains it | A missing page, or a column read as the amount when it was the balance |

`verify` prints these hints automatically when it finds a break.

## Tolerance

Use half a cent, `0.005`. Wide enough to absorb float representation, narrow enough that
a real one-cent error still fires.

Do not widen the tolerance to make a file pass. A tolerance loose enough to hide a
rounding difference is loose enough to hide a wrong digit, and the whole point of the
check is that it does not negotiate.

## What to do when it fails

1. **Look at the row it names.** Nine times out of ten the error is visible in the raw
   line once you know which one to read.
2. **Check the row before it.** A break at row 12 is often caused by row 11 being merged
   into it or split in two.
3. **Check for a missing page** if the totals differ but the chain holds.
4. **Re-run detection.** A wrong decimal convention or date order breaks the whole file
   consistently, which reads as a chain that never holds rather than one that breaks once.
5. **Only then** touch the parser. A rule added to fix one bank usually breaks another,
   so make it conditional on something in that document rather than global.

## The report to keep

Store, next to the extracted table:

- the source file name and its hash
- the opening and closing balance as printed on the statement
- the number of rows, the sum of movements and the verification result
- the date and time of the extraction

That record is what makes the file usable by an accountant six months later. Without it,
a table of transactions is a claim; with it, it is a reconciled document.

## Privacy

A bank statement is among the most sensitive documents a person owns: it carries the
account holder, the IBAN, the balance and a complete map of their life by counterparty.

- Process it locally. Nothing in this skill makes a network call, on purpose.
- Do not paste statement contents into a chat, a shared drive or a log.
- If you keep the extracted table, keep it under the same protection as the original, and
  delete the intermediate text dumps.
