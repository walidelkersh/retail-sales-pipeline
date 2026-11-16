# Retail sales pipeline

This is a medallion pipeline over the UCI Online Retail II dataset, which is two years of invoice lines from a UK online gift retailer. It loads the workbook into bronze as text, cleans it into silver with SQL, and builds a star schema in gold. Every layer is a set of Delta tables, and every transformation is a SQL file that DuckDB runs. The same code runs on one machine and in Microsoft Fabric Python notebooks.

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

## Run it on Fabric

`fabric/deploy.py` uploads the code to a lakehouse and imports three Python notebooks and a data pipeline that runs them in order. It needs the [Fabric CLI](https://microsoft.github.io/fabric-cli/), logged in, and a lakehouse that was created with schemas enabled.

```
uv run python fabric/deploy.py "My workspace.Personal" retail
fab job run "My workspace.Personal/retail_pipeline.DataPipeline"
```

Each notebook runs the same commands as above against the lakehouse, so the checks run there as well, and a failing check fails the pipeline. I ran it on a Fabric trial capacity, where one run takes about three minutes. I compared the row counts of the eleven tables and the net amount with what my machine gives, and they were the same. That comparison was a query in a notebook of my own, and it is not in this repository.

## Power BI

`powerbi/retail-sales.pbip` opens in Power BI Desktop. Each of its five tables is a Power Query that reads one gold Delta table with `DeltaLake.Table` from the folder in the `LakeRoot` parameter, so the parameter has to point at your own `data/lake` before the first refresh. The report has three pages: Overview, Products and Operations.

![The Overview page, with five cards, net revenue by month and net revenue by region](docs/report-overview.png)

The line falls at the end because the data stops on 9 December 2011, so the last month is not a whole month.

I checked it in Power BI Desktop 2.159. After a refresh the Products table totals 19,057,172.70 pounds and the Customers card shows 5,939, which are the numbers that the tests assert.

## Layout

```
pipeline/    bronze ingest, the SQL runner, the check runner
sql/         silver, gold and checks, one statement per file
reference/   retailer country names mapped to ISO codes, written by hand
tests/       small literal fixtures with literal expected values, plus tests on the real data
powerbi/     semantic model and report over the gold tables
fabric/      notebooks, the pipeline definition and the deploy script
docs/        data sources, transformation rules, data model and lineage
```

## What was hard

The two sheets of the workbook overlap. Both contain 1 to 9 December 2010, line for line, which is 22,523 lines, and nothing in the workbook says so. It only shows when the date ranges of the two sheets are put side by side, and counting those nine days twice would inflate December 2010.

Bronze keeps every column as text. Read as text, the dates arrive as Excel serial numbers and a price of 2.55 arrives as 2.5499999999999998, so the typing rules in silver had to be exact, and each one has a test with a literal expected value.

Delta has two timestamp types, and the one without a time zone is not readable by the Fabric SQL analytics endpoint, Direct Lake, Dataflows Gen2 or pipelines. My first version wrote that type without my noticing, because DuckDB picks it for a plain timestamp. I store the invoice time with a UTC label now, and a test asserts that no table uses the newer Delta protocol.

Fabric was harder than I expected, for two reasons. The notebook kernel comes with DuckDB 1.2 and delta-rs 0.18, which are older than the versions that I locked, and it keeps the old DuckDB loaded even after an upgrade, so each notebook runs the pipeline in a separate process that uv builds from `uv.lock`. The second reason is that delta-rs cannot write through the lakehouse mount, because the mount does not allow a file to be renamed. On Fabric the tables are therefore written through the OneLake URL and read through the mount.

I did not use Spark, because one million lines fit on one machine and DuckDB reads and writes the same Delta tables. In total the pipeline is about 200 lines of Python and 18 SQL files.

## What is not done

- On Fabric it runs in my personal workspace on a trial capacity, because my tenant does not let me create a workspace. The pipeline has no schedule, and I started every run by hand.
- The report is not published anywhere and it is not connected to the lakehouse. It reads the gold tables from a local folder, and it has only been opened in Power BI Desktop.
- `fabric/deploy.py` only adds and replaces files, so a file that I delete from the repository stays in the lakehouse until I remove it there.
- Lines that repeat another line of the same invoice exactly are kept, because the workbook has no line number and I cannot tell a double scan from a double export.
- The invoice time has the right clock time and a wrong zone label, which matters only if it is converted to another zone.
- Korea is mapped to South Korea, which is an assumption. The country list itself says it is not authoritative.

## Data and license

I put the code under the MIT license. None of the data is in this repository. Online Retail II is CC BY 4.0 (Chen, D., 2012, https://doi.org/10.24432/C5CG6D) and the country list is CC BY-SA 4.0. `docs/data-sources.md` has the details.
