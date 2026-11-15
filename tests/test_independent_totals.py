from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import openpyxl
import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "data/lake/Files/raw/online_retail_II.xlsx"
FACT = ROOT / "data/lake/Tables/gold/fact_sales"
REJECTED = ROOT / "data/lake/Tables/silver/rejected_lines"
SHEETS = ("Year 2009-2010", "Year 2010-2011")


def text(value):
    if isinstance(value, (int, float)):
        return str(int(value)) if value == int(value) else str(value)
    return "" if value is None else str(value)


def workbook_totals():
    workbook = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)
    try:
        later_invoices = {
            text(row[0])
            for row in workbook[SHEETS[1]].iter_rows(min_row=2, values_only=True)
        }
        totals = Counter()
        years = {2009: Decimal(0), 2010: Decimal(0), 2011: Decimal(0)}
        invoices = set()
        for sheet in SHEETS:
            for row in workbook[sheet].iter_rows(min_row=2, values_only=True):
                invoice, stock, _, quantity, invoice_date, price, customer, _ = row
                invoice, stock = text(invoice), text(stock)
                if sheet == SHEETS[0] and invoice in later_invoices:
                    reason = "sheet_overlap"
                elif invoice.upper().startswith("A"):
                    reason = "bad_debt_adjustment"
                elif stock.upper().startswith("TEST"):
                    reason = "test_stock_code"
                elif price == 0:
                    reason = "unpriced_line"
                elif quantity < 0 and not invoice.upper().startswith("C"):
                    reason = "negative_quantity_without_cancellation"
                else:
                    reason = None
                if reason:
                    totals[reason] += 1
                    continue
                if not isinstance(invoice_date, datetime):
                    invoice_date = datetime(1899, 12, 30) + timedelta(days=invoice_date)
                amount = quantity * Decimal(str(price)).quantize(Decimal("0.001"))
                years[invoice_date.year] += amount
                totals["amount"] += amount
                totals["kept"] += 1
                totals["cancellations"] += invoice.upper().startswith("C")
                totals["quantity"] += quantity
                totals["no_customer"] += customer is None
                invoices.add(invoice)
        totals["invoices"] = len(invoices)
        return totals, years
    finally:
        workbook.close()


@pytest.mark.skipif(not WORKBOOK.exists() or not FACT.exists(), reason="workbook or gold fact table is missing")
def test_independent_totals():
    totals, years = workbook_totals()
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        fact = str(FACT).replace("'", "''")
        rejected = str(REJECTED).replace("'", "''")
        row = connection.execute(f"""
            SELECT count(*), sum(line_amount), count(DISTINCT invoice_no),
                   count(*) FILTER (WHERE is_cancellation), sum(quantity),
                   count(*) FILTER (WHERE customer_key = 0)
            FROM delta_scan('{fact}')
        """).fetchall()[0]
        assert row == (totals["kept"], totals["amount"], totals["invoices"],
                       totals["cancellations"], totals["quantity"], totals["no_customer"])
        actual_years = dict(connection.execute(f"""
            SELECT date_key // 10000, sum(line_amount)
            FROM delta_scan('{fact}') GROUP BY 1
        """).fetchall())
        assert actual_years == years
        actual_reasons = dict(connection.execute(f"""
            SELECT reject_reason, count(*) FROM delta_scan('{rejected}') GROUP BY 1
        """).fetchall())
        reasons = ("sheet_overlap", "bad_debt_adjustment", "test_stock_code",
                   "unpriced_line", "negative_quantity_without_cancellation")
        assert actual_reasons == {reason: totals[reason] for reason in reasons if totals[reason]}
