WITH invoices AS (
    SELECT
        invoice_no,
        customer_id,
        country,
        is_cancellation,
        min(invoice_ts) AS invoice_ts,
        count(*) AS line_count,
        sum(quantity) AS quantity,
        CAST(sum(quantity * unit_price) AS DECIMAL(18,3)) AS order_amount
    FROM silver.invoice_lines
    GROUP BY invoice_no, customer_id, country, is_cancellation
), customer_history AS (
    SELECT
        invoice_no,
        row_number() OVER customer_orders AS customer_order_number,
        date_diff('day', lag(CAST(invoice_ts AS DATE)) OVER customer_orders,
            CAST(invoice_ts AS DATE)) AS days_since_previous_order
    FROM invoices
    -- A cancellation is not an order the customer placed.
    WHERE NOT is_cancellation AND customer_id IS NOT NULL
    WINDOW customer_orders AS (PARTITION BY customer_id ORDER BY invoice_ts, invoice_no)
)
SELECT
    invoices.invoice_no,
    CAST(strftime(invoices.invoice_ts, '%Y%m%d') AS INTEGER) AS date_key,
    CASE WHEN invoices.customer_id IS NULL THEN 0 ELSE customers.customer_key END AS customer_key,
    countries.country_key,
    invoices.is_cancellation,
    invoices.invoice_ts,
    invoices.line_count,
    invoices.quantity,
    invoices.order_amount,
    history.customer_order_number,
    history.days_since_previous_order
FROM invoices
LEFT JOIN customer_history AS history ON invoices.invoice_no = history.invoice_no
LEFT JOIN gold.dim_customer AS customers ON invoices.customer_id = customers.customer_id
LEFT JOIN gold.dim_country AS countries ON invoices.country = countries.retailer_name
