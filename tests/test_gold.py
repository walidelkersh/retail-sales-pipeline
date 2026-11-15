from datetime import date, datetime
from decimal import Decimal

import duckdb
import pytest
from deltalake import write_deltalake

from pipeline.lake import table_path
from pipeline.transform import expose_table, run_layer


@pytest.fixture
def gold_lake(tmp_path):
    with duckdb.connect() as connection:
        connection.execute("""
            CREATE TABLE invoice_lines AS
            SELECT
                invoice_no,
                is_cancellation,
                stock_code,
                description,
                CAST(quantity AS INTEGER) AS quantity,
                CAST(invoice_ts AS TIMESTAMP) AS invoice_ts,
                CAST(unit_price AS DECIMAL(12,3)) AS unit_price,
                CAST(customer_id AS INTEGER) AS customer_id,
                country,
                source_sheet,
                CAST(source_row AS BIGINT) AS source_row
            FROM (VALUES
                ('1', false, '85123A', 'ZEBRA', 1, '2011-12-04 09:00:00',
                 1.250, 20, 'EIRE', 'Year 2010-2011', 1),
                ('2', false, '85123A', 'ZEBRA', 1, '2011-12-02 12:00:00',
                 1.250, 10, 'EIRE', 'Year 2010-2011', 2),
                ('C3', true, '85123A', 'APPLE', -1, '2011-12-02 08:00:00',
                 1.250, 20, 'EIRE', 'Year 2010-2011', 3),
                ('4', false, '85123A', NULL, 1, '2011-12-02 12:00:00',
                 1.250, NULL, 'EIRE', 'Year 2010-2011', 4),
                ('5', false, '85123A', NULL, 1, '2011-12-02 12:00:00',
                 1.250, NULL, 'EIRE', 'Year 2010-2011', 5),
                ('6', false, '85123A', NULL, 1, '2011-12-02 12:00:00',
                 1.250, NULL, 'EIRE', 'Year 2010-2011', 6),
                ('7', false, 'POST', 'ZEBRA', 1, '2011-12-04 12:00:00',
                 1.250, 10, 'Channel Islands', 'Year 2010-2011', 7),
                ('8', false, 'POST', 'APPLE', 1, '2011-12-04 12:00:00',
                 1.250, NULL, 'Channel Islands', 'Year 2010-2011', 8),
                ('9', false, 'DCGS0058', NULL, 1, '2011-12-04 12:00:00',
                 1.250, 30, 'Channel Islands', 'Year 2010-2011', 9)
            ) AS lines(invoice_no, is_cancellation, stock_code, description,
                       quantity, invoice_ts, unit_price, customer_id, country,
                       source_sheet, source_row)
        """)
        connection.execute("""
            CREATE TABLE countries AS
            SELECT *
            FROM (VALUES
                ('EIRE', 'IE', 'IRL', 'Ireland', 'Europe', 'Northern Europe'),
                ('Channel Islands', NULL, NULL, NULL, 'Europe', NULL)
            ) AS countries(retailer_name, alpha_2, alpha_3, iso_name, region, sub_region)
        """)
        for table in ("invoice_lines", "countries"):
            write_deltalake(
                table_path("silver", table, tmp_path),
                connection.table(table),
                mode="overwrite",
            )
    for _ in range(2):
        assert run_layer("gold", tmp_path) == {
            "dim_country": 2, "dim_customer": 4, "dim_date": 3, "dim_product": 3,
            "fact_sales": 9,
        }
    return tmp_path


def test_dim_date(gold_lake):
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        expose_table(connection, table_path("gold", "dim_date", gold_lake))
        dates = connection.sql("SELECT * FROM gold.dim_date ORDER BY date_key")
        assert dates.columns == [
            "date_key", "date", "year", "quarter", "month", "month_name",
            "day_of_week", "day_name", "is_weekend",
        ]
        assert dates.fetchall() == [
            (20111202, date(2011, 12, 2), 2011, 4, 12, "December", 5, "Friday", False),
            (20111203, date(2011, 12, 3), 2011, 4, 12, "December", 6, "Saturday", True),
            (20111204, date(2011, 12, 4), 2011, 4, 12, "December", 7, "Sunday", True),
        ]


def test_dim_product(gold_lake):
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        expose_table(connection, table_path("gold", "dim_product", gold_lake))
        products = connection.sql("SELECT * FROM gold.dim_product ORDER BY product_key")
        assert products.columns == [
            "product_key", "stock_code", "description", "is_merchandise",
        ]
        assert products.fetchall() == [
            (1, "85123A", "ZEBRA", True),
            (2, "DCGS0058", None, False),
            (3, "POST", "APPLE", False),
        ]


def test_dim_customer(gold_lake):
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        expose_table(connection, table_path("gold", "dim_customer", gold_lake))
        customers = connection.sql("SELECT * FROM gold.dim_customer ORDER BY customer_key")
        assert customers.columns == ["customer_key", "customer_id", "first_invoice_date"]
        assert customers.fetchall() == [
            (0, None, None),
            (1, 10, date(2011, 12, 2)),
            (2, 20, date(2011, 12, 2)),
            (3, 30, date(2011, 12, 4)),
        ]


def test_dim_country(gold_lake):
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        expose_table(connection, table_path("gold", "dim_country", gold_lake))
        countries = connection.sql("SELECT * FROM gold.dim_country ORDER BY country_key")
        assert countries.columns == [
            "country_key", "retailer_name", "alpha_2", "alpha_3", "iso_name",
            "region", "sub_region",
        ]
        assert countries.fetchall() == [
            (1, "Channel Islands", None, None, None, "Europe", None),
            (2, "EIRE", "IE", "IRL", "Ireland", "Europe", "Northern Europe"),
        ]


def test_fact_sales(gold_lake):
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        expose_table(connection, table_path("gold", "fact_sales", gold_lake))
        sales = connection.sql("SELECT * FROM gold.fact_sales ORDER BY source_row")
        assert sales.columns == [
            "invoice_no", "date_key", "product_key", "customer_key", "country_key",
            "is_cancellation", "quantity", "unit_price", "line_amount", "invoice_ts",
            "source_sheet", "source_row",
        ]
        assert sales.types[8] == duckdb.sqltype("DECIMAL(18,3)")
        assert sales.fetchall() == [
            ("1", 20111204, 1, 2, 2, False, 1, Decimal("1.250"), Decimal("1.250"),
             datetime(2011, 12, 4, 9), "Year 2010-2011", 1),
            ("2", 20111202, 1, 1, 2, False, 1, Decimal("1.250"), Decimal("1.250"),
             datetime(2011, 12, 2, 12), "Year 2010-2011", 2),
            ("C3", 20111202, 1, 2, 2, True, -1, Decimal("1.250"), Decimal("-1.250"),
             datetime(2011, 12, 2, 8), "Year 2010-2011", 3),
            ("4", 20111202, 1, 0, 2, False, 1, Decimal("1.250"), Decimal("1.250"),
             datetime(2011, 12, 2, 12), "Year 2010-2011", 4),
            ("5", 20111202, 1, 0, 2, False, 1, Decimal("1.250"), Decimal("1.250"),
             datetime(2011, 12, 2, 12), "Year 2010-2011", 5),
            ("6", 20111202, 1, 0, 2, False, 1, Decimal("1.250"), Decimal("1.250"),
             datetime(2011, 12, 2, 12), "Year 2010-2011", 6),
            ("7", 20111204, 3, 1, 1, False, 1, Decimal("1.250"), Decimal("1.250"),
             datetime(2011, 12, 4, 12), "Year 2010-2011", 7),
            ("8", 20111204, 3, 0, 1, False, 1, Decimal("1.250"), Decimal("1.250"),
             datetime(2011, 12, 4, 12), "Year 2010-2011", 8),
            ("9", 20111204, 2, 3, 1, False, 1, Decimal("1.250"), Decimal("1.250"),
             datetime(2011, 12, 4, 12), "Year 2010-2011", 9),
        ]


@pytest.mark.skipif(
    not table_path("silver", "invoice_lines").is_dir(),
    reason="real silver table is absent",
)
def test_real_gold_tables(tmp_path):
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        for table in ("online_retail_lines", "country_names", "country_codes"):
            bronze_path = table_path("bronze", table).as_posix()
            write_deltalake(
                table_path("bronze", table, tmp_path),
                connection.sql("SELECT * FROM delta_scan(?)", params=[bronze_path]),
                mode="overwrite",
            )
    run_layer("silver", tmp_path)
    counts = run_layer("gold", tmp_path)
    assert counts["dim_date"] == 739
    assert counts["dim_country"] == 43
    assert counts["fact_sales"] == 1_038_804
    assert counts["dim_product"] == 4_758
    assert counts["dim_customer"] == 5_940
    with duckdb.connect() as connection:
        connection.execute("INSTALL delta")
        connection.execute("LOAD delta")
        expose_table(connection, table_path("silver", "invoice_lines", tmp_path))
        for table in counts:
            expose_table(connection, table_path("gold", table, tmp_path))
        assert connection.execute("""
            SELECT sum(line_amount), count(DISTINCT invoice_no) FROM gold.fact_sales
        """).fetchall() == [(Decimal("19057172.698"), 48_354)]
        assert connection.execute("""
            SELECT min(date), max(date) FROM gold.dim_date
        """).fetchall() == [(date(2009, 12, 1), date(2011, 12, 9))]
        assert connection.execute("""
            SELECT country FROM silver.invoice_lines
            EXCEPT
            SELECT retailer_name FROM gold.dim_country
        """).fetchall() == []
        assert connection.execute("""
            SELECT stock_code FROM gold.dim_product
            GROUP BY stock_code HAVING count(*) > 1
        """).fetchall() == []
        assert connection.execute("""
            SELECT customer_id FROM gold.dim_customer
            GROUP BY customer_id HAVING count(*) > 1
        """).fetchall() == []
