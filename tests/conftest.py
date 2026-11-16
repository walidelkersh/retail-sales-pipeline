import duckdb
import pytest
from deltalake import write_deltalake

from pipeline.lake import table_path
from pipeline.transform import run_layer


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
                CAST(invoice_ts AS TIMESTAMP) AT TIME ZONE 'UTC' AS invoice_ts,
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
