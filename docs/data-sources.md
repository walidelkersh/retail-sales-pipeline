# Data sources

The pipeline reads three sources. The two downloaded ones are not committed to this repository, because each has its own license and I would rather point to the original than redistribute a copy.

## Online Retail II

The transactions come from the Online Retail II dataset in the UCI Machine Learning Repository (Chen, D., 2012, https://doi.org/10.24432/C5CG6D), which is licensed under CC BY 4.0. It is one workbook, `online_retail_II.xlsx`, and its two sheets hold the invoice lines of a UK online gift retailer between 1 December 2009 and 9 December 2011.

| Sheet | Lines |
|---|---|
| Year 2009-2010 | 525,461 |
| Year 2010-2011 | 541,910 |

Both sheets have the same eight columns: Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID and Country. `pipeline/bronze.py` downloads the zip from the UCI site and stops if its SHA-256 does not match the one written in the code, because a source that changed without notice would make every number in these documents wrong.

## Country codes

The workbook only gives a country name, so I added a list of ISO 3166 codes and UN regions from https://github.com/lukes/ISO-3166-Countries-with-Regional-Codes, which is licensed under CC BY-SA 4.0. The download is fixed to one commit and one checksum, and it has 249 rows. Its own README says that the list is merged from Wikipedia and the UN M49 standard and that it is not authoritative. That is enough to group sales by region, but it would not be enough for anything legal.

## Retailer country names

The names in the workbook do not match the ISO names, because the workbook says EIRE, RSA and USA. `reference/country_names.csv` maps each of the 43 names to an alpha-2 code. I wrote this file by hand, and it is the only source that lives in the repository.

Four names have no single ISO country: Channel Islands, European Community, West Indies and Unspecified. They carry a fallback region and no code. I mapped Korea to KR, which is an assumption, because the workbook does not say which Korea it means.

## How the sources arrive in bronze

Every source lands in a Delta table under `Tables/bronze` with all of its columns kept as text. I did this because typing a column is a decision, and I wanted every decision to be visible in the silver SQL and not hidden in the reader. The invoice lines also get `source_sheet` and `source_row`, which together identify one line all the way to the fact table, and every table gets `ingested_at`.

| Bronze table | Rows |
|---|---|
| online_retail_lines | 1,067,371 |
| country_codes | 249 |
| country_names | 43 |

`uv run python -m pipeline.bronze` prints these counts, and `tests/test_bronze.py` asserts them against the real files.
