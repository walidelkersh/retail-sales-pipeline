import hashlib
from pathlib import Path
from zipfile import ZipFile

import duckdb
import pytest
from openpyxl import Workbook

from pipeline import bronze
from pipeline.lake import raw_directory, table_path


@pytest.fixture
def workbook(tmp_path):
    columns = [
        "Invoice", "StockCode", "Description", "Quantity", "InvoiceDate",
        "Price", "Customer ID", "Country",
    ]
    workbook = tmp_path / "lines.xlsx"
    book = Workbook()
    first = book.active
    first.title = "Year 2009-2010"
    second = book.create_sheet("Year 2010-2011")
    first.append(columns)
    second.append(columns)
    first.append(["C100", "001", "tea & cups", -2, 40148.5, 6.95, None, "United Kingdom"])
    first.append(["101", "002", None, 1, 40149, 0, None, "France"])
    first.append(["C100", "001", "tea & cups", -2, 40148.5, 6.95, None, "United Kingdom"])
    second.append(["102", "003", "mug", 3, 40544, 1.25, 42, "Germany"])
    book.save(workbook)
    return workbook


def test_bronze_preserves_lines_and_replaces_on_rerun(workbook, tmp_path):
    expected = [
        ("C100", "001", "tea & cups", "-2", "40148.5",
         "6.95", None, "United Kingdom", "Year 2009-2010", 1),
        ("101", "002", None, "1", "40149", "0", None, "France", "Year 2009-2010", 2),
        ("C100", "001", "tea & cups", "-2", "40148.5",
         "6.95", None, "United Kingdom", "Year 2009-2010", 3),
        ("102", "003", "mug", "3", "40544", "1.25", "42", "Germany", "Year 2010-2011", 1),
    ]
    for _ in range(2):
        assert bronze.ingest_workbook(workbook, tmp_path) == {
            "Year 2009-2010": 3, "Year 2010-2011": 1,
        }
        with duckdb.connect() as connection:
            path = table_path("bronze", "online_retail_lines", tmp_path).as_posix()
            connection.execute("INSTALL delta")
            connection.execute("LOAD delta")
            assert connection.execute(
                "SELECT * EXCLUDE (ingested_at) FROM delta_scan(?) ORDER BY source_sheet, source_row",
                [path],
            ).fetchall() == expected
            assert connection.execute(
                "SELECT count(ingested_at), any_value(typeof(ingested_at)) FROM delta_scan(?)",
                [path],
            ).fetchall() == [(4, "TIMESTAMP WITH TIME ZONE")]


def test_download_and_cached_archive(workbook, tmp_path, monkeypatch):
    archive = tmp_path / "fixture.zip"
    with ZipFile(archive, "w") as zipped:
        zipped.write(workbook, bronze.WORKBOOK_NAME)
    with archive.open("rb") as zipped:
        checksum = hashlib.file_digest(zipped, "sha256").hexdigest()
    monkeypatch.setattr(bronze, "ZIP_SHA256", checksum)
    downloads = []

    def download(url, destination):
        downloads.append(url)
        destination.write_bytes(archive.read_bytes())

    monkeypatch.setattr(bronze, "urlretrieve", download)
    lake_root = tmp_path / "lake"
    for _ in range(2):
        extracted = bronze.download_workbook(lake_root)
        assert extracted == raw_directory(lake_root) / "online_retail_II.xlsx"
        assert extracted.read_bytes() == workbook.read_bytes()
    assert downloads == [bronze.ZIP_URL]


def test_checksum_mismatch_stops_before_extraction(tmp_path):
    raw = raw_directory(tmp_path)
    raw.mkdir(parents=True)
    (raw / "online_retail_ii.zip").write_bytes(b"wrong zip")
    with pytest.raises(ValueError, match=f"SHA256 mismatch.*expected {bronze.ZIP_SHA256}, got"):
        bronze.download_workbook(tmp_path)
    assert not (raw / bronze.WORKBOOK_NAME).exists()


@pytest.mark.skipif(
    not Path("data/lake/Files/raw/online_retail_II.xlsx").is_file(),
    reason="real workbook is absent",
)
def test_real_workbook_sheet_counts(tmp_path):
    workbook = Path("data/lake/Files/raw/online_retail_II.xlsx")
    assert bronze.ingest_workbook(workbook, tmp_path) == {
        "Year 2009-2010": 525_461,
        "Year 2010-2011": 541_910,
    }
    with duckdb.connect() as connection:
        path = table_path("bronze", "online_retail_lines", tmp_path).as_posix()
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        counts = connection.execute(
            "SELECT source_sheet, count(*) FROM delta_scan(?) GROUP BY source_sheet ORDER BY source_sheet",
            [path],
        ).fetchall()
    assert counts == [("Year 2009-2010", 525_461), ("Year 2010-2011", 541_910)]
