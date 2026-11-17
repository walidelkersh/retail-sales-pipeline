# Transformation rules

Bronze changes nothing. Every rule below is one expression in `sql/silver` or `sql/gold`, and every count comes from the real workbook and is asserted in `tests/test_silver.py` or `tests/test_gold.py`.

## Silver: typed invoice lines

`sql/silver/invoice_lines.sql` turns the text columns of bronze into typed ones.

| Silver column | Bronze column | Rule |
|---|---|---|
| invoice_no | Invoice | unchanged |
| is_cancellation | Invoice | true when the invoice starts with C |
| stock_code | StockCode | upper-cased, because the workbook writes the same code both ways (79323p and 79323P) |
| description | Description | outer spaces removed |
| quantity | Quantity | integer |
| invoice_ts | InvoiceDate | Excel serial day to timestamp with a UTC label, with day 0 on 1899-12-30, rounded to the second because the serial is a float |
| unit_price | Price | DECIMAL(12,3), because a few lines are priced at 0.001 and two decimals would turn them into 0 |
| customer_id | Customer ID | integer, null when the workbook has no customer |
| country | Country | unchanged |
| source_sheet, source_row | the same | unchanged, they are the key of a line |

I keep the UK wall-clock time because the workbook gives no time zone. I store it with a UTC label because the zone-less Delta timestamp is not readable by the Fabric SQL analytics endpoint, Direct Lake, Dataflows Gen2 or pipelines. The clock time is right and the zone label is not, which matters only if I convert it to another zone.

## Silver: rejected lines

`sql/silver/00.rejected_lines.sql` holds the reject rules, and it is the only place where they exist. A line takes the first reason that applies, in this order, and it goes to `silver.rejected_lines` with its bronze text untouched.

| Order | Reason | Rule | Lines |
|---|---|---|---|
| 1 | sheet_overlap | the line is in sheet Year 2009-2010 and its invoice also appears in sheet Year 2010-2011 | 22,523 |
| 2 | bad_debt_adjustment | the invoice starts with A | 6 |
| 3 | test_stock_code | the stock code starts with TEST | 17 |
| 4 | unpriced_line | the price is 0 | 6,021 |
| 5 | negative_quantity_without_cancellation | the quantity is below 0 and the invoice is not a cancellation | 0 |

The overlap is the largest rule because both sheets contain 1 to 9 December 2010, line for line, and counting those days twice would inflate December 2010. I kept the copy in the later sheet.

Rule 5 catches nothing on this data, because every line of that kind also has a price of 0 and rule 4 reaches it first. I left it in because a priced line with a negative quantity and no cancellation would otherwise pass as a sale.

The three numbers reconcile: 1,038,804 kept lines and 28,567 rejected lines are the 1,067,371 lines of bronze.

## What I kept on purpose

- Cancellations stay in silver with their negative quantities, so the net amount is the sales minus what was cancelled.
- Lines that repeat another line of the same invoice exactly stay. The workbook has no line number, so I cannot tell a product that was scanned twice from a line that was exported twice, and I would rather keep a real sale than delete it on a guess.
- Lines with no customer stay. In gold they point to the unknown customer, which has key 0.
- Stock codes that are not products, such as POST for postage, stay. `gold.dim_product` marks them with `is_merchandise` false, so a report can leave them out.

## Gold

- `dim_product.description` is the most frequent description of a stock code, because the same code is described in more than one way over the two years. A tie goes to the alphabetically first.
- `dim_date` has one row for every day between the first and the last invoice, including the days with no invoice.
- `fact_sales.line_amount` is quantity times unit price.
- `fact_orders` rolls the lines of an invoice up to one row. Its timestamp is the earliest one of its lines, because the lines of one invoice can be a few minutes apart.
- `fact_orders.customer_order_number` numbers the sales of a customer in time order, and the invoice number breaks a tie. `days_since_previous_order` counts calendar days. A cancellation gets no number because it is not an order that the customer placed, and an invoice with no customer gets none because I cannot tell whose history it belongs to.
- A first order is the first one inside the two years of data, because a customer may have ordered before 1 December 2009.
- Surrogate keys are numbered in the order of the natural key, so the same data gives the same keys on every run.

## Checks

`uv run python -m pipeline.checks silver` and `uv run python -m pipeline.checks gold` run the queries in `sql/checks`. Each query returns the rows that break a rule, so zero rows is a pass, and a failing run names every check that failed and not only the first.

| Layer | Check |
|---|---|
| silver | bronze lines = kept lines + rejected lines |
| silver | (source_sheet, source_row) is unique |
| silver | required columns are never null |
| silver | price above 0, quantity not 0, a sale has a positive quantity, the timestamp is inside the period of the source |
| silver | every reject reason is one of the five |
| gold | the fact table has one row for every silver line |
| gold | (source_sheet, source_row) is unique in the fact table |
| gold | every key in the fact table exists in its dimension |
| gold | dimension keys are unique |
| gold | line amount = quantity times unit price |
| gold | fact_orders has exactly one row for every invoice in fact_sales, with the same line count, quantity and amount |
| gold | the order numbers of a customer run from 1 with no gap and no repeat |

There is no check that a cancellation has a negative quantity, because one real cancellation line does not.
