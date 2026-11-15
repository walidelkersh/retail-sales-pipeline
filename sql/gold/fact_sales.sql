SELECT
    lines.invoice_no,
    CAST(strftime(lines.invoice_ts, '%Y%m%d') AS INTEGER) AS date_key,
    products.product_key,
    CASE WHEN lines.customer_id IS NULL THEN 0 ELSE customers.customer_key END AS customer_key,
    countries.country_key,
    lines.is_cancellation,
    lines.quantity,
    lines.unit_price,
    CAST(lines.quantity * lines.unit_price AS DECIMAL(18,3)) AS line_amount,
    lines.invoice_ts,
    lines.source_sheet,
    lines.source_row
FROM silver.invoice_lines AS lines
LEFT JOIN gold.dim_product AS products ON lines.stock_code = products.stock_code
LEFT JOIN gold.dim_customer AS customers ON lines.customer_id = customers.customer_id
LEFT JOIN gold.dim_country AS countries ON lines.country = countries.retailer_name
