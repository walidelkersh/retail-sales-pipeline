# Retail sales pipeline

This is a medallion pipeline over the UCI Online Retail II dataset, which is two years of invoice lines from a UK online gift retailer. It loads the workbook into bronze as text, cleans it into silver with SQL, and builds a star schema in gold. Every layer is a set of Delta tables, and every transformation is a SQL file that DuckDB runs.

| | |
|---|---|
| Invoice lines read | 1,067,371 |
| Lines kept | 1,038,804 |
| Lines rejected, each with a reason | 28,567 |
| Distinct invoices | 48,354 |
| Net amount | 19,057,172.698 pounds |

These numbers are asserted in `tests/test_silver.py` and `tests/test_gold.py`, and `tests/test_independent_totals.py` recomputes them from the workbook in plain Python, without the pipeline code or SQL, and compares.

## Run it

It needs Python 3.11 or later and [uv](https://docs.astral.sh/uv/). On the first run it downloads the workbook (45 MB), the country list and two DuckDB extensions.

```
uv sync
uv run python -m pipeline.bronze
uv run python -m pipeline.transform silver
uv run python -m pipeline.checks silver
uv run python -m pipeline.transform gold
uv run python -m pipeline.checks gold
uv run pytest
```

The tables are written under `data/lake`, which is not committed. On a fresh clone the tests that need the real data are skipped until the pipeline has run.

## Layout

```
pipeline/    bronze ingest, the SQL runner, the check runner
sql/         silver, gold and checks, one statement per file
reference/   retailer country names mapped to ISO codes, written by hand
tests/       literal fixtures with hand-computed answers, plus tests on the real data
powerbi/     semantic model over the gold tables
docs/        data sources, transformation rules, data model and lineage
```

## What was hard

The two sheets of the workbook overlap. Both contain 1 to 9 December 2010, line for line, which is 22,523 lines, and nothing in the workbook says so. It only shows when the date ranges of the two sheets are put side by side, and counting those nine days twice would inflate December 2010.

Bronze keeps every column as text. Read as text, the dates arrive as Excel serial numbers and a price of 2.55 arrives as 2.5499999999999998, so the typing rules in silver had to be exact, and each one has a test with a literal expected value.

Delta has two timestamp types, and the one without a time zone is not readable by the Fabric SQL analytics endpoint, Direct Lake, Dataflows Gen2 or pipelines. My first version wrote that type without my noticing, because DuckDB picks it for a plain timestamp. I store the invoice time with a UTC label now, and a test asserts that no table uses the newer Delta protocol.

I did not use Spark, because one million lines fit on one machine and DuckDB reads and writes the same Delta tables. In total the pipeline is about 200 lines of Python and 18 SQL files.

## What is not done

- It has not run on Microsoft Fabric yet. It is written for Fabric Python notebooks, which come with DuckDB and delta-rs, but I have only run it on my own machine.
- The Power BI semantic model in `powerbi/` parses with the Microsoft tabular library, but I have not opened it in Power BI Desktop or refreshed it yet.
- Lines that repeat another line of the same invoice exactly are kept, because the workbook has no line number and I cannot tell a double scan from a double export.
- The invoice time has the right clock time and a wrong zone label, which matters only if it is converted to another zone.
- Korea is mapped to South Korea, which is an assumption. The country list itself says it is not authoritative.

## Data and license

I put the code under the MIT license. None of the data is in this repository. Online Retail II is CC BY 4.0 (Chen, D., 2012, https://doi.org/10.24432/C5CG6D) and the country list is CC BY-SA 4.0. `docs/data-sources.md` has the details.
