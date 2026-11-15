SELECT
    0 AS customer_key,
    NULL AS customer_id,
    NULL AS first_invoice_date
UNION ALL
SELECT
    row_number() OVER (ORDER BY customer_id) AS customer_key,
    customer_id,
    CAST(min(invoice_ts) AS DATE) AS first_invoice_date
FROM silver.invoice_lines
WHERE customer_id IS NOT NULL
GROUP BY customer_id
