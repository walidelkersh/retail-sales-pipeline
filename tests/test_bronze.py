import hashlib
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import duckdb
import pytest
from deltalake import DeltaTable

from pipeline import bronze
from pipeline.lake import raw_directory, table_path


@pytest.fixture
def workbook(tmp_path):
    columns = [
        "Invoice", "StockCode", "Description", "Quantity", "InvoiceDate",
        "Price", "Customer ID", "Country",
    ]
    cancellation = [
        "C100", "001", "tea & cups", "-2", "40148.322916666664",
        "2.5499999999999998", None, "United Kingdom",
    ]
    sheets = [
        ("Year 2009-2010", [
            cancellation,
            ["101", "002", None, "1", "40149", "0", None, "France"],
            cancellation,
        ]),
        ("Year 2010-2011", [
            ["102", "003", "mug", "3", "40544", "1.25", "0042", "Germany"],
        ]),
    ]
    workbook = tmp_path / "lines.xlsx"
    with ZipFile(workbook, "w", ZIP_DEFLATED) as zipped:
        zipped.writestr("[Content_Types].xml", '''
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
</Types>''')
        zipped.writestr("_rels/.rels", '''
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')
        sheet_entries = []
        sheet_links = []
        for sheet_number, (sheet_name, lines) in enumerate(sheets, 1):
            sheet_entries.append(
                f'<sheet name="{sheet_name}" sheetId="{sheet_number}" r:id="rId{sheet_number}"/>'
            )
            sheet_links.append(
                f'<Relationship Id="rId{sheet_number}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{sheet_number}.xml"/>'
            )
            sheet_rows = []
            for row_number, line in enumerate([columns, *lines], 1):
                cells = []
                for column_number, text in enumerate(line):
                    if text is None:
                        continue
                    address = f"{chr(65 + column_number)}{row_number}"
                    if row_number > 1 and column_number in (3, 4, 5):
                        cells.append(f'<c r="{address}"><v>{text}</v></c>')
                    else:
                        cells.append(
                            f'<c r="{address}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'
                        )
                sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
            zipped.writestr(
                f"xl/worksheets/sheet{sheet_number}.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>',
            )
        zipped.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(sheet_entries)}</sheets></workbook>',
        )
        zipped.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(sheet_links)}</Relationships>',
        )
    return workbook


def test_bronze_preserves_lines_and_replaces_on_rerun(workbook, tmp_path):
    expected = [
        ("C100", "001", "tea & cups", "-2", "40148.322916666664",
         "2.5499999999999998", None, "United Kingdom", "Year 2009-2010", 1),
        ("101", "002", None, "1", "40149", "0", None, "France", "Year 2009-2010", 2),
        ("C100", "001", "tea & cups", "-2", "40148.322916666664",
         "2.5499999999999998", None, "United Kingdom", "Year 2009-2010", 3),
        ("102", "003", "mug", "3", "40544", "1.25", "0042", "Germany", "Year 2010-2011", 1),
    ]
    for _ in range(2):
        assert bronze.ingest_workbook(workbook, tmp_path) == {
            "Year 2009-2010": 3, "Year 2010-2011": 1,
        }
        table = DeltaTable(table_path("bronze", "online_retail_lines", tmp_path))
        with duckdb.connect() as connection:
            lines = connection.read_parquet(table.file_uris()).order("source_sheet, source_row")
            assert lines.project("* EXCLUDE (ingested_at)").fetchall() == expected
            assert lines.aggregate(
                "count(ingested_at), any_value(typeof(ingested_at))"
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
    table = DeltaTable(table_path("bronze", "online_retail_lines", tmp_path))
    with duckdb.connect() as connection:
        counts = connection.read_parquet(table.file_uris()).aggregate(
            "source_sheet, count(*)", "source_sheet"
        ).order("source_sheet").fetchall()
    assert counts == [("Year 2009-2010", 525_461), ("Year 2010-2011", 541_910)]
