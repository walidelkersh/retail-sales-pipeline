import hashlib
from pathlib import Path
from urllib.request import urlretrieve
from xml.etree import ElementTree
from zipfile import ZipFile

import duckdb
from deltalake import write_deltalake

from pipeline.lake import LAKE_ROOT, raw_directory, table_path


ZIP_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
ZIP_SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
WORKBOOK_NAME = "online_retail_II.xlsx"
COUNTRY_CODES_URL = (
    "https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/"
    "145f1ad3caff212ed25f42b0ee2c8b92a75af895/all/all.csv"
)
COUNTRY_CODES_SHA256 = "347bba35029f804f53780062052499781d267b8a5d887bf3b051e80a68390d6d"
COUNTRY_NAMES = Path(__file__).resolve().parents[1] / "reference" / "country_names.csv"


def download_source(url, destination, expected_checksum):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        urlretrieve(url, destination)
    with destination.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    if checksum != expected_checksum:
        raise ValueError(
            f"SHA256 mismatch for {destination}: expected {expected_checksum}, got {checksum}"
        )
    return destination


def download_workbook(lake_root=LAKE_ROOT):
    raw = raw_directory(lake_root)
    archive = download_source(ZIP_URL, raw / "online_retail_ii.zip", ZIP_SHA256)
    workbook = raw / WORKBOOK_NAME
    if not workbook.exists():
        with ZipFile(archive) as zipped:
            zipped.extract(WORKBOOK_NAME, raw)
    return workbook


def ingest_workbook(workbook, lake_root=LAKE_ROOT):
    with ZipFile(workbook) as zipped:
        sheets = ElementTree.fromstring(zipped.read("xl/workbook.xml")).findall(
            "{*}sheets/{*}sheet"
        )
    sheet_queries = []
    sheet_parameters = []
    for sheet in sheets:
        sheet_queries.append(
            "SELECT *, ?::VARCHAR AS source_sheet, "
            "row_number() OVER () AS source_row, current_timestamp AS ingested_at "
            "FROM read_xlsx(?, sheet=?, header=true, all_varchar=true, "
            "stop_at_empty=false)"
        )
        sheet_parameters.extend([sheet.attrib["name"], str(workbook), sheet.attrib["name"]])
    with duckdb.connect() as connection:
        connection.execute("INSTALL excel")
        connection.execute("LOAD excel")
        connection.execute(
            "CREATE TEMP TABLE online_retail_lines AS " + " UNION ALL ".join(sheet_queries),
            sheet_parameters,
        )
        write_deltalake(
            table_path("bronze", "online_retail_lines", lake_root),
            connection.table("online_retail_lines"),
            mode="overwrite",
        )
        return dict(connection.execute(
            "SELECT source_sheet, count(*) FROM online_retail_lines "
            "GROUP BY source_sheet ORDER BY source_sheet"
        ).fetchall())


def ingest_reference(reference, table, lake_root=LAKE_ROOT):
    with duckdb.connect() as connection:
        connection.execute(
            "CREATE TEMP TABLE country_reference AS "
            "SELECT *, current_timestamp AS ingested_at "
            "FROM read_csv(?, all_varchar=true, header=true, nullstr='')",
            [str(reference)],
        )
        write_deltalake(
            table_path("bronze", table, lake_root),
            connection.table("country_reference"),
            mode="overwrite",
        )
        return connection.execute("SELECT count(*) FROM country_reference").fetchall()[0][0]


if __name__ == "__main__":
    for sheet, line_count in ingest_workbook(download_workbook()).items():
        print(f"{sheet}: {line_count}")
    country_codes = download_source(
        COUNTRY_CODES_URL, raw_directory() / "country_codes.csv", COUNTRY_CODES_SHA256,
    )
    for reference, table in ((country_codes, "country_codes"), (COUNTRY_NAMES, "country_names")):
        print(f"{table}: {ingest_reference(reference, table)}")
