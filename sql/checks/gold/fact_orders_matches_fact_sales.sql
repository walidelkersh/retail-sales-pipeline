WITH sales AS (
    SELECT
        invoice_no,
        count(*) AS line_count,
        sum(quantity) AS quantity,
        sum(line_amount) AS order_amount
    FROM gold.fact_sales
    GROUP BY invoice_no
), orders AS (
    SELECT
        invoice_no,
        count(*) AS order_count,
        sum(line_count) AS line_count,
        sum(quantity) AS quantity,
        sum(order_amount) AS order_amount
    FROM gold.fact_orders
    GROUP BY invoice_no
)
SELECT *
FROM sales
FULL OUTER JOIN orders USING (invoice_no)
WHERE sales.invoice_no IS NULL
    OR orders.order_count IS DISTINCT FROM 1
    OR sales.line_count IS DISTINCT FROM orders.line_count
    OR sales.quantity IS DISTINCT FROM orders.quantity
    OR sales.order_amount IS DISTINCT FROM orders.order_amount
