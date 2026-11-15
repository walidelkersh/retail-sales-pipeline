from decimal import Decimal

import duckdb
import pytest
from deltalake import write_deltalake

from pipeline.lake import table_path
from pipeline.transform import expose_table, run_layer


@pytest.fixture
def bronze_lake(tmp_path):
    with duckdb.connect() as connection:
        connection.execute("""
            CREATE TABLE online_retail_lines AS
            SELECT *, current_timestamp AS ingested_at
            FROM (VALUES
                ('489434', '79323p', '  PINK CHERRY LIGHTS ', '12',
                 '40148.322916666664', '2.5499999999999998', '13085',
                 'United Kingdom', 'Year 2009-2010', 1),
                ('489434', '79323p', '  PINK CHERRY LIGHTS ', '12',
                 '40148.322916666664', '2.5499999999999998', '13085',
                 'United Kingdom', 'Year 2009-2010', 2),
                ('536365', '003', 'TEA', '1', '40513', '2.5', '13085',
                 'United Kingdom', 'Year 2009-2010', 3),
                ('C489449', '001', NULL, '-12', '40544', '1E-3', NULL,
                 'France', 'Year 2010-2011', 1),
                ('c489450', '002', 'MUG', '-1', '40544', '1.25', NULL,
                 'Germany', 'Year 2010-2011', 2),
                ('536365', '003', 'TEA', '1', '40513', '2.5', '13085',
                 'United Kingdom', 'Year 2010-2011', 3),
                ('A563186', 'B', 'Adjust bad debt', '1', '40544', '-1', NULL,
                 'United Kingdom', 'Year 2010-2011', 4),
                ('a563187', 'B', 'Adjust bad debt', '1', '40544', '0', NULL,
                 'United Kingdom', 'Year 2010-2011', 5),
                ('563188', 'TeSt001', 'TEST', '1', '40544', '1', NULL,
                 'United Kingdom', 'Year 2010-2011', 6),
                ('563189', '004', 'MUG', '1', '40544', '0', NULL,
                 'United Kingdom', 'Year 2010-2011', 7),
                ('563190', '005', 'MUG', '-1', '40544', '1', NULL,
                 'United Kingdom', 'Year 2010-2011', 8)
            ) AS lines("Invoice", "StockCode", "Description", "Quantity",
                       "InvoiceDate", "Price", "Customer ID", "Country",
                       source_sheet, source_row)
        """)
        write_deltalake(
            table_path("bronze", "online_retail_lines", tmp_path),
            connection.table("online_retail_lines"),
            mode="overwrite",
        )
    return tmp_path


def test_silver_types_and_preserves_lines(bronze_lake, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for _ in range(2):
        assert run_layer("silver", bronze_lake) == {
            "rejected_lines": 6, "invoice_lines": 5,
        }
        with duckdb.connect() as connection:
            connection.execute("INSTALL delta")
            connection.execute("LOAD delta")
            path = table_path("silver", "invoice_lines", tmp_path).as_posix()
            invoice_lines = connection.sql(
                "SELECT * REPLACE (CAST(invoice_ts AS VARCHAR) AS invoice_ts) "
                "FROM delta_scan(?) ORDER BY source_sheet, source_row",
                params=[path],
            )
            assert invoice_lines.columns == [
                "invoice_no", "is_cancellation", "stock_code", "description",
                "quantity", "invoice_ts", "unit_price", "customer_id", "country",
                "source_sheet", "source_row",
            ]
            assert invoice_lines.fetchall() == [
                ("489434", False, "79323P", "PINK CHERRY LIGHTS", 12,
                 "2009-12-01 07:45:00", Decimal("2.550"), 13085,
                 "United Kingdom", "Year 2009-2010", 1),
                ("489434", False, "79323P", "PINK CHERRY LIGHTS", 12,
                 "2009-12-01 07:45:00", Decimal("2.550"), 13085,
                 "United Kingdom", "Year 2009-2010", 2),
                ("C489449", True, "001", None, -12,
                 "2011-01-01 00:00:00", Decimal("0.001"), None,
                 "France", "Year 2010-2011", 1),
                ("c489450", True, "002", "MUG", -1,
                 "2011-01-01 00:00:00", Decimal("1.250"), None,
                 "Germany", "Year 2010-2011", 2),
                ("536365", False, "003", "TEA", 1,
                 "2010-12-01 00:00:00", Decimal("2.500"), 13085,
                 "United Kingdom", "Year 2010-2011", 3),
            ]


def test_silver_rejects_and_reconciles_lines(bronze_lake):
    counts = run_layer("silver", bronze_lake)
    assert counts == {"rejected_lines": 6, "invoice_lines": 5}
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        expose_table(connection, table_path("bronze", "online_retail_lines", bronze_lake))
        expose_table(connection, table_path("silver", "rejected_lines", bronze_lake))
        expose_table(connection, table_path("silver", "invoice_lines", bronze_lake))
        assert connection.execute("""
            SELECT source_sheet, source_row, reject_reason
            FROM silver.rejected_lines
            ORDER BY source_sheet, source_row
        """).fetchall() == [
            ("Year 2009-2010", 3, "sheet_overlap"),
            ("Year 2010-2011", 4, "bad_debt_adjustment"),
            ("Year 2010-2011", 5, "bad_debt_adjustment"),
            ("Year 2010-2011", 6, "test_stock_code"),
            ("Year 2010-2011", 7, "unpriced_line"),
            ("Year 2010-2011", 8, "negative_quantity_without_cancellation"),
        ]
        assert connection.execute("""
            SELECT source_sheet, source_row
            FROM silver.invoice_lines
            ORDER BY source_sheet, source_row
        """).fetchall() == [
            ("Year 2009-2010", 1),
            ("Year 2009-2010", 2),
            ("Year 2010-2011", 1),
            ("Year 2010-2011", 2),
            ("Year 2010-2011", 3),
        ]
        bronze_count = connection.execute(
            "SELECT count(*) FROM bronze.online_retail_lines"
        ).fetchall()[0][0]
        assert bronze_count == counts["invoice_lines"] + counts["rejected_lines"]
        assert connection.execute("""
            SELECT * EXCLUDE (reject_reason) FROM silver.rejected_lines
            EXCEPT ALL
            SELECT * EXCLUDE (ingested_at) FROM bronze.online_retail_lines
        """).fetchall() == []


@pytest.mark.skipif(
    not table_path("bronze", "online_retail_lines").is_dir(),
    reason="real bronze table is absent",
)
def test_real_bronze_reject_counts(tmp_path):
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        bronze_path = table_path("bronze", "online_retail_lines").as_posix()
        write_deltalake(
            table_path("bronze", "online_retail_lines", tmp_path),
            connection.sql("SELECT * FROM delta_scan(?)", params=[bronze_path]),
            mode="overwrite",
        )
    counts = run_layer("silver", tmp_path)
    assert counts["invoice_lines"] + counts["rejected_lines"] == 1_067_371
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        path = table_path("silver", "rejected_lines", tmp_path).as_posix()
        reasons = dict(connection.execute(
            "SELECT reject_reason, count(*) FROM delta_scan(?) GROUP BY reject_reason",
            [path],
        ).fetchall())
    assert reasons == {
        "sheet_overlap": 22_523,
        "bad_debt_adjustment": 6,
        "test_stock_code": 17,
        "unpriced_line": 6_021,
    }
    assert counts["invoice_lines"] == 1_038_804
