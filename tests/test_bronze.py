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


@pytest.fixture
def country_codes(tmp_path):
    countries = tmp_path / "country_codes.csv"
    countries.write_text(
        "name,alpha-2,alpha-3,country-code,iso_3166-2,region,sub-region,"
        "intermediate-region,region-code,sub-region-code,intermediate-region-code\n"
        'Namibia,NA,NAM,516,ISO 3166-2:NA,Africa,Sub-Saharan Africa,Southern Africa,002,202,018\n'
        'Antarctica,AQ,ATA,010,ISO 3166-2:AQ,"","","","","",""\n',
        encoding="utf-8",
    )
    return countries


def test_country_codes_preserve_text_and_replace_on_rerun(country_codes, tmp_path):
    expected = [
        ("Antarctica", "AQ", "ATA", "010", "ISO 3166-2:AQ", None, None, None, None, None, None),
        ("Namibia", "NA", "NAM", "516", "ISO 3166-2:NA", "Africa", "Sub-Saharan Africa",
         "Southern Africa", "002", "202", "018"),
    ]
    for _ in range(2):
        assert bronze.ingest_reference(country_codes, "country_codes", tmp_path) == 2
        with duckdb.connect() as connection:
            path = table_path("bronze", "country_codes", tmp_path).as_posix()
            connection.execute("INSTALL delta")
            connection.execute("LOAD delta")
            assert connection.execute(
                "SELECT * EXCLUDE (ingested_at) FROM delta_scan(?) ORDER BY name",
                [path],
            ).fetchall() == expected
            assert connection.execute(
                "SELECT count(ingested_at), any_value(typeof(ingested_at)) FROM delta_scan(?)",
                [path],
            ).fetchall() == [(2, "TIMESTAMP WITH TIME ZONE")]


def test_retailer_country_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert bronze.ingest_reference(bronze.COUNTRY_NAMES, "country_names", tmp_path) == 43
    with duckdb.connect() as connection:
        path = table_path("bronze", "country_names", tmp_path).as_posix()
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        assert connection.execute(
            "SELECT count(*), count(DISTINCT retailer_name), "
            "count(*) FILTER (WHERE (alpha_2 IS NULL) = (fallback_region IS NULL)) "
            "FROM delta_scan(?)",
            [path],
        ).fetchall() == [(43, 43, 0)]
        assert connection.execute(
            "SELECT retailer_name, alpha_2 FROM delta_scan(?) "
            "WHERE retailer_name IN ('EIRE', 'RSA', 'USA') ORDER BY retailer_name",
            [path],
        ).fetchall() == [("EIRE", "IE"), ("RSA", "ZA"), ("USA", "US")]


@pytest.mark.skipif(
    not Path("data/lake/Files/raw/country_codes.csv").is_file(),
    reason="real country codes are absent",
)
def test_real_country_codes_cover_retailer_countries(tmp_path):
    countries = Path("data/lake/Files/raw/country_codes.csv")
    assert bronze.ingest_reference(countries, "country_codes", tmp_path) == 249
    assert bronze.ingest_reference(bronze.COUNTRY_NAMES, "country_names", tmp_path) == 43
    with duckdb.connect() as connection:
        codes_path = table_path("bronze", "country_codes", tmp_path).as_posix()
        names_path = table_path("bronze", "country_names", tmp_path).as_posix()
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        assert connection.execute(
            "SELECT count(*) FROM delta_scan(?)", [codes_path],
        ).fetchall() == [(249,)]
        assert connection.execute(
            'SELECT alpha_2 FROM delta_scan(?) WHERE alpha_2 IS NOT NULL '
            'EXCEPT SELECT "alpha-2" FROM delta_scan(?)',
            [names_path, codes_path],
        ).fetchall() == []


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
