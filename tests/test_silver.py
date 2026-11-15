from decimal import Decimal

import duckdb
from deltalake import write_deltalake

from pipeline.lake import table_path
from pipeline.transform import run_layer


def test_silver_types_and_preserves_lines(tmp_path, monkeypatch):
    with duckdb.connect() as connection:
        connection.execute("""
            CREATE TABLE online_retail_lines AS
            SELECT *, current_timestamp AS ingested_at
            FROM (VALUES
                ('489434', '79323p', '  PINK CHERRY LIGHTS ', '12',
                 '40148.322916666664', '2.5499999999999998', '13085',
                 'United Kingdom', 'Year 2009-2010', 1),
                ('C489449', '001', NULL, '-12', '40544', '1E-3', NULL,
                 'France', 'Year 2010-2011', 1),
                ('c489450', '002', 'MUG', '-1', '40544', '0', NULL,
                 'Germany', 'Year 2010-2011', 2)
            ) AS lines("Invoice", "StockCode", "Description", "Quantity",
                       "InvoiceDate", "Price", "Customer ID", "Country",
                       source_sheet, source_row)
        """)
        bronze_count = connection.execute(
            "SELECT count(*) FROM online_retail_lines"
        ).fetchall()[0][0]
        write_deltalake(
            table_path("bronze", "online_retail_lines", tmp_path),
            connection.table("online_retail_lines"),
            mode="overwrite",
        )
    monkeypatch.chdir(tmp_path)
    for _ in range(2):
        assert run_layer("silver", tmp_path) == {"invoice_lines": 3}
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
                ("C489449", True, "001", None, -12,
                 "2011-01-01 00:00:00", Decimal("0.001"), None,
                 "France", "Year 2010-2011", 1),
                ("c489450", True, "002", "MUG", -1,
                 "2011-01-01 00:00:00", Decimal("0.000"), None,
                 "Germany", "Year 2010-2011", 2),
            ]
            assert connection.execute(
                "SELECT count(*) FROM delta_scan(?)", [path]
            ).fetchall() == [(bronze_count,)]
