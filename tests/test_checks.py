import duckdb
import pytest
from deltalake import write_deltalake

from pipeline.checks import run_checks
from pipeline.lake import table_path
from pipeline.transform import lake_connection, run_layer


@pytest.fixture
def checks_lake(tmp_path):
    with duckdb.connect() as connection:
        write_deltalake(
            table_path("bronze", "online_retail_lines", tmp_path),
            connection.sql("""
                SELECT * FROM (VALUES
                    ('Year 2009-2010', 1),
                    ('Year 2010-2011', 1),
                    ('Year 2010-2011', 2),
                    ('Year 2010-2011', 3),
                    ('Year 2010-2011', 4),
                    ('Year 2010-2011', 5),
                    ('Year 2010-2011', 6),
                    ('Year 2010-2011', 7)
                ) AS lines(source_sheet, source_row)
            """),
            mode="overwrite",
        )
        write_deltalake(
            table_path("silver", "invoice_lines", tmp_path),
            connection.sql("""
                SELECT * FROM (VALUES
                    ('489434', FALSE, '001', 'MUG', 1,
                     TIMESTAMPTZ '2009-12-01 00:00:00+00', CAST(1 AS DECIMAL(12,3)), 13085,
                     'United Kingdom', 'Year 2009-2010', 1),
                    ('C489449', TRUE, '002', NULL, -1,
                     TIMESTAMPTZ '2011-01-01 00:00:00+00', CAST(0.001 AS DECIMAL(12,3)), NULL,
                     'France', 'Year 2010-2011', 1),
                    ('C489450', TRUE, '003', 'TEA', 1,
                     TIMESTAMPTZ '2011-12-09 23:59:59+00', CAST(2.5 AS DECIMAL(12,3)), NULL,
                     'Germany', 'Year 2010-2011', 2)
                ) AS lines(invoice_no, is_cancellation, stock_code, description,
                           quantity, invoice_ts, unit_price, customer_id, country,
                           source_sheet, source_row)
            """),
            mode="overwrite",
        )
        write_deltalake(
            table_path("silver", "rejected_lines", tmp_path),
            connection.sql("""
                SELECT * FROM (VALUES
                    ('Year 2010-2011', 3, 'sheet_overlap'),
                    ('Year 2010-2011', 4, 'bad_debt_adjustment'),
                    ('Year 2010-2011', 5, 'test_stock_code'),
                    ('Year 2010-2011', 6, 'unpriced_line'),
                    ('Year 2010-2011', 7, 'negative_quantity_without_cancellation')
                ) AS lines(source_sheet, source_row, reject_reason)
            """),
            mode="overwrite",
        )
    return tmp_path


def test_silver_checks_pass(checks_lake, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run_checks("silver", checks_lake) == {
        "invoice_lines_key_is_unique": 0,
        "invoice_lines_required_columns": 0,
        "invoice_lines_values_in_range": 0,
        "rejected_lines_reason_is_known": 0,
        "silver_reconciles_with_bronze": 0,
    }


def test_silver_checks_report_all_failures(checks_lake):
    with lake_connection(checks_lake) as connection:
        write_deltalake(
            table_path("silver", "invoice_lines", checks_lake),
            connection.sql("""
                SELECT * REPLACE (
                    1 AS source_row,
                    CASE WHEN is_cancellation THEN 0 ELSE unit_price END::DECIMAL(12,3) AS unit_price
                ) FROM silver.invoice_lines
            """),
            mode="overwrite",
        )
        write_deltalake(
            table_path("silver", "rejected_lines", checks_lake),
            connection.sql("""
                SELECT * REPLACE (
                    CASE
                        WHEN source_row = 3 THEN NULL
                        WHEN source_row = 4 THEN 'unknown'
                        ELSE reject_reason
                    END AS reject_reason
                ) FROM silver.rejected_lines
            """),
            mode="overwrite",
        )
    with pytest.raises(ValueError) as failure:
        run_checks("silver", checks_lake)
    assert str(failure.value) == (
        "Checks failed: invoice_lines_key_is_unique: 1; "
        "invoice_lines_values_in_range: 2; rejected_lines_reason_is_known: 2"
    )


def test_silver_checks_missing_column_and_count(checks_lake):
    with lake_connection(checks_lake) as connection:
        write_deltalake(
            table_path("silver", "invoice_lines", checks_lake),
            connection.sql("""
                SELECT * REPLACE (CAST(NULL AS VARCHAR) AS country)
                FROM silver.invoice_lines WHERE NOT is_cancellation
            """),
            mode="overwrite",
        )
    with pytest.raises(ValueError) as failure:
        run_checks("silver", checks_lake)
    assert str(failure.value) == (
        "Checks failed: invoice_lines_required_columns: 1; "
        "silver_reconciles_with_bronze: 1"
    )


@pytest.fixture
def gold_checks_lake(checks_lake):
    with lake_connection(checks_lake) as connection:
        write_deltalake(
            table_path("silver", "countries", checks_lake),
            connection.sql("""
                SELECT * FROM (VALUES
                    ('United Kingdom', 'GB', 'GBR', 'United Kingdom', 'Europe', 'Northern Europe'),
                    ('France', 'FR', 'FRA', 'France', 'Europe', 'Western Europe'),
                    ('Germany', 'DE', 'DEU', 'Germany', 'Europe', 'Western Europe')
                ) AS countries(retailer_name, alpha_2, alpha_3, iso_name, region, sub_region)
            """),
            mode="overwrite",
        )
    run_layer("gold", checks_lake)
    return checks_lake


def test_gold_checks_pass(gold_checks_lake, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run_checks("gold", gold_checks_lake) == {
        "dimension_keys_are_unique": 0,
        "fact_orders_matches_fact_sales": 0,
        "fact_orders_numbers_are_contiguous": 0,
        "fact_sales_amount_is_quantity_times_price": 0,
        "fact_sales_key_is_unique": 0,
        "fact_sales_keys_resolve": 0,
        "fact_sales_matches_silver": 0,
    }


def test_gold_checks_report_all_failures(gold_checks_lake):
    with lake_connection(gold_checks_lake) as connection:
        write_deltalake(
            table_path("gold", "fact_sales", gold_checks_lake),
            connection.sql("""
                SELECT * REPLACE (
                    CAST(NULL AS INTEGER) AS date_key,
                    -1 AS product_key,
                    CAST(NULL AS BIGINT) AS customer_key,
                    -1 AS country_key,
                    CAST(line_amount + 1 AS DECIMAL(18,3)) AS line_amount
                ) FROM gold.fact_sales WHERE NOT is_cancellation
                UNION ALL
                SELECT * FROM gold.fact_sales
            """),
            mode="overwrite",
        )
        write_deltalake(
            table_path("gold", "dim_country", gold_checks_lake),
            connection.sql("""
                SELECT * FROM gold.dim_country
                UNION ALL
                SELECT * FROM gold.dim_country WHERE country_key = 1
            """),
            mode="overwrite",
        )
    with pytest.raises(ValueError) as failure:
        run_checks("gold", gold_checks_lake)
    assert str(failure.value) == (
        "Checks failed: dimension_keys_are_unique: 1; "
        "fact_orders_matches_fact_sales: 1; "
        "fact_sales_amount_is_quantity_times_price: 1; fact_sales_key_is_unique: 1; "
        "fact_sales_keys_resolve: 1; fact_sales_matches_silver: 1"
    )


@pytest.mark.parametrize("check, replacement, count", [
    ("fact_orders_matches_fact_sales", "CAST(order_amount + 1 AS DECIMAL(18,3)) AS order_amount", 3),
    ("fact_orders_numbers_are_contiguous", "customer_order_number + 1 AS customer_order_number", 1),
])
def test_fact_orders_checks_catch_faults(gold_checks_lake, check, replacement, count):
    with lake_connection(gold_checks_lake) as connection:
        write_deltalake(
            table_path("gold", "fact_orders", gold_checks_lake),
            connection.sql(f"SELECT * REPLACE ({replacement}) FROM gold.fact_orders"),
            mode="overwrite",
        )
    with pytest.raises(ValueError) as failure:
        run_checks("gold", gold_checks_lake)
    assert str(failure.value) == f"Checks failed: {check}: {count}"


@pytest.mark.skipif(
    not table_path("silver", "invoice_lines").is_dir(),
    reason="real silver table is absent",
)
def test_real_silver_checks():
    assert run_checks("silver") == {
        "invoice_lines_key_is_unique": 0,
        "invoice_lines_required_columns": 0,
        "invoice_lines_values_in_range": 0,
        "rejected_lines_reason_is_known": 0,
        "silver_reconciles_with_bronze": 0,
    }
    if all(table_path("gold", table).is_dir() for table in ("fact_sales", "fact_orders")):
        assert run_checks("gold") == {
            "dimension_keys_are_unique": 0,
            "fact_orders_matches_fact_sales": 0,
            "fact_orders_numbers_are_contiguous": 0,
            "fact_sales_amount_is_quantity_times_price": 0,
            "fact_sales_key_is_unique": 0,
            "fact_sales_keys_resolve": 0,
            "fact_sales_matches_silver": 0,
        }
