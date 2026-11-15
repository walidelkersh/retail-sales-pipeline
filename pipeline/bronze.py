import hashlib
from urllib.request import urlretrieve
from xml.etree import ElementTree
from zipfile import ZipFile

import duckdb
from deltalake import write_deltalake

from pipeline.lake import LAKE_ROOT, raw_directory, table_path


ZIP_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
ZIP_SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
WORKBOOK_NAME = "online_retail_II.xlsx"


def download_workbook(lake_root=LAKE_ROOT):
    raw = raw_directory(lake_root)
    raw.mkdir(parents=True, exist_ok=True)
    archive = raw / "online_retail_ii.zip"
    if not archive.exists():
        urlretrieve(ZIP_URL, archive)
    with archive.open("rb") as zipped:
        checksum = hashlib.file_digest(zipped, "sha256").hexdigest()
    if checksum != ZIP_SHA256:
        raise ValueError(
            f"SHA256 mismatch for {archive}: expected {ZIP_SHA256}, got {checksum}"
        )
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


if __name__ == "__main__":
    for sheet, line_count in ingest_workbook(download_workbook()).items():
        print(f"{sheet}: {line_count}")
