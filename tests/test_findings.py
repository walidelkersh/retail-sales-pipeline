from decimal import Decimal

import pytest

from pipeline.lake import table_path
from pipeline.transform import lake_connection


@pytest.mark.skipif(
    not table_path("gold", "fact_orders").is_dir(),
    reason="real gold tables are absent",
)
def test_findings_in_readme():
    with lake_connection("data/lake") as connection:
        q = lambda sql: connection.execute(sql).fetchall()
        assert q("""
            SELECT date_key // 100 FROM gold.fact_sales
            GROUP BY 1 ORDER BY sum(line_amount) DESC LIMIT 2
        """) == [(201111,), (201011,)]
        assert q("""
            SELECT date_key // 10000, sum(line_amount) FROM gold.fact_sales
            WHERE date_key % 10000 < 1201 GROUP BY 1 ORDER BY 1
        """) == [(2010, Decimal("8498611.094")), (2011, Decimal("8576184.964"))]
        assert q("""
            SELECT round(100 * sum(line_amount) FILTER (WHERE retailer_name = 'United Kingdom')
                / sum(line_amount), 1)
            FROM gold.fact_sales JOIN gold.dim_country USING (country_key)
        """) == [(84.9,)]
        assert q("""
            WITH customers AS (
                SELECT customer_key, sum(line_amount) AS revenue FROM gold.fact_sales
                WHERE customer_key <> 0 GROUP BY 1
            ), top_one_percent AS (
                SELECT revenue FROM customers ORDER BY revenue DESC
                LIMIT (SELECT count(*) // 100 FROM customers)
            )
            SELECT round(100 * (SELECT sum(revenue) FROM top_one_percent) / sum(revenue), 1)
            FROM customers
        """) == [(31.2,)]
        assert q("""
            SELECT
                round(100 * count(DISTINCT customer_key) FILTER (WHERE customer_order_number = 2)
                    / count(DISTINCT customer_key) FILTER (WHERE customer_order_number = 1), 1),
                round(100 * sum(order_amount) FILTER (WHERE customer_order_number > 1)
                    / sum(order_amount) FILTER (WHERE customer_order_number IS NOT NULL), 1),
                median(days_since_previous_order)
            FROM gold.fact_orders
        """) == [(72.4, 86.0, 25.0)]
        assert q("""
            SELECT round(100 * -sum(line_amount) FILTER (WHERE is_cancellation)
                / sum(line_amount) FILTER (WHERE NOT is_cancellation), 2)
            FROM gold.fact_sales
        """) == [(7.14,)]
        assert q("""
            SELECT day_name, count(DISTINCT invoice_no) FROM gold.fact_sales
            JOIN gold.dim_date USING (date_key)
            WHERE NOT is_cancellation AND day_name IN ('Saturday', 'Sunday')
            GROUP BY 1 ORDER BY 1
        """) == [("Saturday", 30), ("Sunday", 4_835)]
