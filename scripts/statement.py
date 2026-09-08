#!/usr/bin/env python3
"""statement - turn a bank statement into a table you can check.

Extraction is the easy half. The half that matters is proving the extraction is right,
and a bank statement carries its own proof: every running balance must equal the
previous balance plus the movement. If the chain holds from the opening balance to the
closing balance, the parse is correct. If it breaks, it tells you exactly which row is
wrong.

  pdftotext -layout statement.pdf - | statement.py parse - --out rows.csv
  statement.py verify rows.csv --opening 1240.55 --closing 2103.11
  statement.py detect  rows.csv

Pure standard library, Python 3.8+. No network, no dependencies. Nothing is uploaded.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter

# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------

DATE_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?\b")
ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def parse_date(token, day_first=True, default_year=None):
    """Return ISO yyyy-mm-dd, or None.

    dd/mm and mm/dd are genuinely ambiguous below the 13th, and no amount of cleverness
    resolves a single row. It is resolved per DOCUMENT: if any date in the file has a
    first component above 12, the whole file is day-first. Guessing per row produces a
    statement where January and October are silently swapped.
    """
    m = ISO_RE.search(token)
    if m:
        return "%s-%s-%s" % m.groups()
    m = DATE_RE.search(token)
    if not m:
        return None
    a, b, y = m.group(1), m.group(2), m.group(3)
    day, month = (a, b) if day_first else (b, a)
    day, month = int(day), int(month)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    if y is None:
        if default_year is None:
            return None
        year = default_year
    else:
        year = int(y)
        if year < 100:
            year += 2000 if year < 70 else 1900
    return "%04d-%02d-%02d" % (year, month, day)


def infer_day_first(text):
    """Day-first if any date has a first component above 12."""
    for a, b, _ in DATE_RE.findall(text):
        if int(a) > 12:
            return True
        if int(b) > 12:
            return False
    return True   # European statements are the common case for this tool


# --------------------------------------------------------------------------
# amounts
# --------------------------------------------------------------------------

AMOUNT_RE = re.compile(r"(?<![\w/])[-+(]?\s?\d{1,3}(?:[.\s']\d{3})*(?:[.,]\d{1,2})?\)?"
                       r"(?:\s?(?:CR|DR|C|D))?(?![\w/])")


def infer_decimal_comma(text):
    """Decide the decimal separator once per document.

    1.234,56 and 1,234.56 are the same number written by two different worlds. Deciding
    per value turns 1.234 into either 1234 or 1.234 depending on the row, and the totals
    then miss by three orders of magnitude on exactly the rows where it matters.
    """
    comma_dec = len(re.findall(r"\d,\d{2}\b", text))
    dot_dec = len(re.findall(r"\d\.\d{2}\b", text))
    return comma_dec >= dot_dec


def parse_amount(token, decimal_comma=True):
    """Handle 1.234,56 / 1,234.56 / (123,45) / 123,45- / 123,45 CR."""
    if token is None:
        return None
    t = token.strip()
    if not t:
        return None
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative = True
        t = t[1:-1]
    if t.endswith("-"):
        negative = True
        t = t[:-1]
    suffix = re.search(r"\s?(CR|DR|C|D)$", t, re.IGNORECASE)
    if suffix:
        if suffix.group(1).upper() in ("DR", "D"):
            negative = True
        t = t[:suffix.start()]
    t = t.strip().replace(" ", "").replace("'", "")
    if t.startswith("-"):
        negative = True
        t = t[1:]
    if t.startswith("+"):
        t = t[1:]
    if decimal_comma:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        value = float(t)
    except ValueError:
        return None
    return -value if negative else value


def find_amounts(line, decimal_comma=True):
    """Amounts in a statement line, left to right, with their positions."""
    out = []
    for m in AMOUNT_RE.finditer(line):
        raw = m.group(0)
        if not re.search(r"\d", raw):
            continue
        # a bare integer with no separator and fewer than 3 digits is usually
        # a reference or a day, not money
        if not re.search(r"[.,]\d{1,2}\b", raw) and len(re.sub(r"\D", "", raw)) < 4:
            continue
        value = parse_amount(raw, decimal_comma)
        if value is not None:
            out.append({"raw": raw.strip(), "value": value,
                        "start": m.start(), "end": m.end()})
    return out


# --------------------------------------------------------------------------
# line parsing
# --------------------------------------------------------------------------

NOISE = re.compile(
    r"^\s*(pag(ina)?\.?\s*\d|page\s*\d|segue|continua|riporto|carried forward|"
    r"saldo (iniziale|finale|precedente)|opening balance|closing balance|"
    r"balance (brought|carried) forward|data\s+valuta|data\s+contabile|"
    r"descrizione|causale|dare\s+avere|date\s+description)",
    re.IGNORECASE)


def parse_lines(text, day_first=None, decimal_comma=None, default_year=None):
    """Parse `pdftotext -layout` output into transactions.

    Two document-level decisions are made once, from the whole text, before any row is
    read: day-first versus month-first, and comma versus dot as the decimal separator.
    Both are wrong to decide per row.

    A transaction line has a date AND at least one amount. A line with neither is a
    continuation of the previous transaction's description: bank descriptions routinely
    run to three lines, and a parser that treats each line as a row produces a file with
    three times the rows and a third of the money.
    """
    if day_first is None:
        day_first = infer_day_first(text)
    if decimal_comma is None:
        decimal_comma = infer_decimal_comma(text)

    rows = []
    skipped = 0
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if NOISE.match(line):
            skipped += 1
            continue

        amounts = find_amounts(line, decimal_comma)
        date = parse_date(line[:24], day_first, default_year)

        if date and amounts:
            first_amount_at = amounts[0]["start"]
            date_match = DATE_RE.search(line[:24]) or ISO_RE.search(line[:24])
            desc_start = date_match.end() if date_match else 0
            description = line[desc_start:first_amount_at].strip()
            # a second date right after the first is the value date
            value_date = None
            second = DATE_RE.match(description)
            if second:
                value_date = parse_date(second.group(0), day_first, default_year)
                description = description[second.end():].strip()
            rows.append({
                "date": date,
                "value_date": value_date or "",
                "description": re.sub(r"\s{2,}", " ", description),
                "amount": amounts[-2]["value"] if len(amounts) >= 2 else amounts[0]["value"],
                "balance": amounts[-1]["value"] if len(amounts) >= 2 else None,
                "raw_amounts": [a["raw"] for a in amounts],
            })
        elif rows and not date and not amounts and len(line.strip()) > 2:
            rows[-1]["description"] = re.sub(
                r"\s{2,}", " ", (rows[-1]["description"] + " " + line.strip()).strip())
        else:
            skipped += 1

    return {"rows": rows, "skipped": skipped,
            "day_first": day_first, "decimal_comma": decimal_comma}


# --------------------------------------------------------------------------
# the part that matters: verification
# --------------------------------------------------------------------------

def verify(rows, opening=None, closing=None, tolerance=0.005):
    """A statement carries its own proof. Check it, do not trust the parse.

    Two independent checks:
      1. the balance chain: balance[i] == balance[i-1] + amount[i], row by row
      2. the total: opening + sum(amounts) == closing

    The first localises an error to a row. The second catches a whole missing page,
    which the chain will not notice if the page boundary happens to be consistent.
    """
    problems = []
    with_balance = [r for r in rows if r.get("balance") is not None]
    chain_checked = 0
    for i in range(1, len(with_balance)):
        prev, cur = with_balance[i - 1], with_balance[i]
        expected = prev["balance"] + cur["amount"]
        chain_checked += 1
        if abs(expected - cur["balance"]) > tolerance:
            problems.append({
                "type": "chain_break",
                "index": i,
                "date": cur.get("date"),
                "description": (cur.get("description") or "")[:48],
                "previous_balance": round(prev["balance"], 2),
                "amount": round(cur["amount"], 2),
                "expected_balance": round(expected, 2),
                "found_balance": round(cur["balance"], 2),
                "difference": round(cur["balance"] - expected, 2),
            })

    total = sum(r["amount"] for r in rows if r.get("amount") is not None)
    result = {
        "rows": len(rows),
        "rows_with_balance": len(with_balance),
        "chain_checks": chain_checked,
        "chain_breaks": len([p for p in problems if p["type"] == "chain_break"]),
        "sum_of_movements": round(total, 2),
        "problems": problems,
    }
    if opening is not None and closing is not None:
        expected_closing = opening + total
        result["opening"] = opening
        result["closing"] = closing
        result["expected_closing"] = round(expected_closing, 2)
        result["total_difference"] = round(closing - expected_closing, 2)
        result["totals_match"] = abs(closing - expected_closing) <= tolerance
    result["ok"] = (result["chain_breaks"] == 0
                    and result.get("totals_match", True))
    return result


def explain_difference(difference, rows, tolerance=0.005):
    """A difference that equals a row you can see is a row that was read twice or missed.

    Three signatures worth naming, because each has a different fix.
    """
    hints = []
    d = abs(difference)
    if d <= tolerance:
        return hints
    for r in rows:
        a = r.get("amount")
        if a is None:
            continue
        if abs(abs(a) - d) <= tolerance:
            hints.append("the difference equals the amount on %s %r: that row is "
                         "probably duplicated or missing"
                         % (r.get("date"), (r.get("description") or "")[:36]))
            break
        if abs(2 * abs(a) - d) <= tolerance:
            hints.append("the difference is twice the amount on %s: that row was "
                         "probably read with the wrong sign" % r.get("date"))
            break
    if not hints:
        if abs(d - round(d)) < 1e-9 and d >= 1000:
            hints.append("a round difference of this size usually means a thousands "
                         "separator was read as a decimal point on one row")
        else:
            hints.append("no single row explains it: check for a missing page, or a "
                         "column read as the amount when it was the balance")
    return hints


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

FIELDS = ["date", "value_date", "description", "amount", "balance"]


def read_text(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def read_rows(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            row = {k: (v or "").strip() for k, v in r.items()}
            for key in ("amount", "balance"):
                if row.get(key) not in (None, ""):
                    try:
                        row[key] = float(row[key])
                    except ValueError:
                        row[key] = None
                else:
                    row[key] = None
            rows.append(row)
    return rows


def cmd_parse(args):
    text = read_text(args.source)
    result = parse_lines(text, args.day_first, args.decimal_comma, args.year)
    rows = result["rows"]
    print("format: %s dates, %s decimal separator"
          % ("day-first" if result["day_first"] else "month-first",
             "comma" if result["decimal_comma"] else "dot"))
    print("%d transaction(s), %d line(s) skipped as headers, footers or noise"
          % (len(rows), result["skipped"]))
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in FIELDS})
        print("written to %s" % args.out)
    else:
        for r in rows[:args.preview]:
            print("  %s  %-44s %10.2f  %s"
                  % (r["date"], r["description"][:44], r["amount"],
                     "" if r["balance"] is None else "%12.2f" % r["balance"]))
    if rows and all(r["balance"] is None for r in rows):
        print("\nNo running balance column was found, so the chain cannot be verified.")
        print("Check whether the balance is in a column the layout put on its own line.")
    return 0


def cmd_verify(args):
    rows = read_rows(args.source)
    result = verify(rows, args.opening, args.closing, args.tolerance)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    print("rows                %d (%d carry a balance)"
          % (result["rows"], result["rows_with_balance"]))
    print("chain checks        %d" % result["chain_checks"])
    print("chain breaks        %d" % result["chain_breaks"])
    print("sum of movements    %.2f" % result["sum_of_movements"])
    if "expected_closing" in result:
        print("opening + movements %.2f" % result["expected_closing"])
        print("stated closing      %.2f" % result["closing"])
        print("difference          %.2f" % result["total_difference"])
    print("\n%s" % ("VERIFIED: the parse reproduces the statement exactly."
                    if result["ok"] else
                    "NOT VERIFIED: the parse does not reproduce the statement."))
    for p in result["problems"][:args.max_problems]:
        print("\n  break at row %d, %s  %s" % (p["index"], p["date"], p["description"]))
        print("    %.2f %+.2f should give %.2f, the statement says %.2f (off by %.2f)"
              % (p["previous_balance"], p["amount"], p["expected_balance"],
                 p["found_balance"], p["difference"]))
        for hint in explain_difference(p["difference"], rows, args.tolerance):
            print("    hint: %s" % hint)
    if "total_difference" in result and not result.get("totals_match", True):
        print("\n  totals differ by %.2f" % result["total_difference"])
        for hint in explain_difference(result["total_difference"], rows, args.tolerance):
            print("    hint: %s" % hint)
    return 0 if result["ok"] else 1


def cmd_detect(args):
    text = read_text(args.source)
    day_first = infer_day_first(text)
    decimal_comma = infer_decimal_comma(text)
    dates = DATE_RE.findall(text)
    print("dates found            %d" % len(dates))
    print("date order             %s" % ("day-first (dd/mm)" if day_first
                                         else "month-first (mm/dd)"))
    print("decimal separator      %s" % ("comma (1.234,56)" if decimal_comma
                                         else "dot (1,234.56)"))
    years = Counter(y for _, _, y in dates if y)
    if years:
        print("years present          %s" % ", ".join(sorted(years)))
    else:
        print("years present          none: pass --year, and mind a statement that "
              "crosses December")
    if not dates:
        print("\nNo dates at all. This is almost certainly a scanned statement with no "
              "text layer.\nRun OCR first; see references/extraction.md.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="statement", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("parse", help="layout text in, transactions out")
    a.add_argument("source", help="output of `pdftotext -layout`, or - for stdin")
    a.add_argument("--out")
    a.add_argument("--preview", type=int, default=12)
    a.add_argument("--year", type=int, help="for statements whose rows omit the year")
    a.add_argument("--day-first", dest="day_first", action="store_true", default=None)
    a.add_argument("--month-first", dest="day_first", action="store_false")
    a.add_argument("--decimal-comma", dest="decimal_comma", action="store_true", default=None)
    a.add_argument("--decimal-dot", dest="decimal_comma", action="store_false")
    a.set_defaults(func=cmd_parse)

    v = sub.add_parser("verify", help="prove the parse against the balance chain")
    v.add_argument("source")
    v.add_argument("--opening", type=float)
    v.add_argument("--closing", type=float)
    v.add_argument("--tolerance", type=float, default=0.005)
    v.add_argument("--max-problems", type=int, default=5)
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_verify)

    d = sub.add_parser("detect", help="what format is this statement in")
    d.add_argument("source")
    d.set_defaults(func=cmd_detect)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
