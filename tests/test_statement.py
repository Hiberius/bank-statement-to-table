#!/usr/bin/env python3
"""Zero-dependency test suite. Run: python3 tests/test_statement.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import statement as S  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s %s" % (name, detail))
        FAILED.append(name)


print("dates")
check("iso passes through", S.parse_date("2026-06-01") == "2026-06-01")
check("day first", S.parse_date("01/06/2026", day_first=True) == "2026-06-01")
check("month first", S.parse_date("01/06/2026", day_first=False) == "2026-01-06")
check("two digit year becomes 2000s", S.parse_date("01/06/26") == "2026-06-01")
check("dots as separators", S.parse_date("01.06.2026") == "2026-06-01")
check("missing year uses the default", S.parse_date("01/06", default_year=2026) == "2026-06-01")
check("missing year with no default is rejected", S.parse_date("01/06") is None)
check("impossible month is rejected", S.parse_date("01/13/2026", day_first=True) is None)
check("garbage is rejected", S.parse_date("hello") is None)

print("date order is decided per document, not per row")
check("a day above 12 anywhere makes the file day-first",
      S.infer_day_first("05/03/2026 and 21/03/2026"))
check("a second component above 12 makes it month-first",
      not S.infer_day_first("03/21/2026 and 05/03/2026"))
check("ambiguous text defaults to day-first", S.infer_day_first("05/03/2026"))

print("amounts")
check("european thousands and decimal", S.parse_amount("1.234,56", True) == 1234.56)
check("anglo thousands and decimal", S.parse_amount("1,234.56", False) == 1234.56)
check("negative sign", S.parse_amount("-82,40", True) == -82.40)
check("trailing minus", S.parse_amount("82,40-", True) == -82.40)
check("parentheses mean negative", S.parse_amount("(82,40)", True) == -82.40)
check("DR suffix means negative", S.parse_amount("82.40 DR", False) == -82.40)
check("CR suffix stays positive", S.parse_amount("82.40 CR", False) == 82.40)
check("apostrophe thousands", S.parse_amount("1'234.56", False) == 1234.56)
check("garbage is rejected", S.parse_amount("abc", True) is None)

print("the decimal separator is decided per document")
check("comma statement detected", S.infer_decimal_comma("1.234,56 e 82,40"))
check("dot statement detected", not S.infer_decimal_comma("1,234.56 and 82.40"))

print("line parsing")
text = """SALDO INIZIALE AL 01/06/2026                              1.240,55
Data       Valuta     Descrizione                    Importo      Saldo
01/06/2026 01/06/2026 BONIFICO DA ACME SRL          1.500,00    2.740,55
                      FATTURA 2026-114 SALDO
03/06/2026 03/06/2026 PAGAMENTO POS                   -82,40    2.658,15
Pagina 1 di 2
"""
r = S.parse_lines(text)
rows = r["rows"]
check("two transactions found", len(rows) == 2)
check("the value date is separated from the booking date",
      rows[0]["value_date"] == "2026-06-01")
check("a continuation line joins the previous description",
      "FATTURA 2026-114" in rows[0]["description"])
check("a continuation line does not become its own row",
      all("FATTURA" not in x["description"] or x["amount"] == 1500.0 for x in rows))
check("the amount is the second to last number", rows[0]["amount"] == 1500.0)
check("the balance is the last number", rows[0]["balance"] == 2740.55)
check("page footers are skipped", r["skipped"] >= 2)
check("the opening balance line is not a transaction",
      all(x["amount"] != 1240.55 for x in rows))
check("negative amounts survive", rows[1]["amount"] == -82.40)

print("verification catches what the eye does not")
good = [{"amount": 1500.0, "balance": 2740.55, "date": "2026-06-01", "description": "a"},
        {"amount": -82.40, "balance": 2658.15, "date": "2026-06-03", "description": "b"},
        {"amount": -119.90, "balance": 2538.25, "date": "2026-06-05", "description": "c"}]
v = S.verify(good, opening=1240.55, closing=2538.25)
check("a correct parse verifies", v["ok"])
check("no chain breaks on a correct parse", v["chain_breaks"] == 0)
check("totals match on a correct parse", v["totals_match"])

broken = [dict(r) for r in good]
broken[1]["amount"] = -8.24        # a decimal read in the wrong place
v = S.verify(broken, opening=1240.55, closing=2538.25)
check("a misread decimal breaks the chain", not v["ok"])
check("the break is localised to the row", v["problems"][0]["index"] == 1)
check("the expected balance is reported",
      abs(v["problems"][0]["expected_balance"] - 2732.31) < 0.01)

missing = [good[0], good[2]]
v = S.verify(missing, opening=1240.55, closing=2538.25)
check("a missing row breaks the chain", v["chain_breaks"] == 1)
hints = S.explain_difference(v["problems"][0]["difference"], good)
check("the hint names a row that explains the difference",
      any("duplicated or missing" in h for h in hints))

flipped = [dict(r) for r in good]
flipped[1]["amount"] = 82.40       # sign read the wrong way round
flipped[1]["balance"] = 2658.15
v = S.verify(flipped, opening=1240.55, closing=2538.25)
hints = S.explain_difference(v["problems"][0]["difference"], flipped)
check("a flipped sign is diagnosed as such",
      any("wrong sign" in h for h in hints))

v = S.verify(good, opening=1240.55, closing=9999.99)
check("a wrong closing balance is caught even when the chain holds",
      v["chain_breaks"] == 0 and not v["ok"])

v = S.verify(good)
check("verification runs without opening and closing", v["ok"])
check("rows without a balance are not chain checked",
      S.verify([{"amount": 10.0, "balance": None}])["chain_checks"] == 0)

print("end to end on the sample statement")
with open(os.path.join(HERE, "..", "templates", "statement.example.txt"),
          encoding="utf-8") as fh:
    sample = fh.read()
r = S.parse_lines(sample)
check("seven transactions parsed", len(r["rows"]) == 7)
check("detected as day-first", r["day_first"])
check("detected as comma decimal", r["decimal_comma"])
v = S.verify(r["rows"], opening=1240.55, closing=2103.11)
check("the sample statement verifies exactly", v["ok"], str(v.get("total_difference")))
check("sum of movements matches the statement",
      abs(v["sum_of_movements"] - 862.56) < 0.01)

print("")
if FAILED:
    print("%d test(s) failed: %s" % (len(FAILED), ", ".join(FAILED)))
    sys.exit(1)
print("all tests passed")
