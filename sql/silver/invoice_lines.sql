SELECT
    "Invoice" AS invoice_no,
    upper("Invoice") LIKE 'C%' AS is_cancellation,
    upper("StockCode") AS stock_code,
    trim("Description") AS description,
    CAST("Quantity" AS INTEGER) AS quantity,
    -- Excel serials carry float noise below a second.
    (TIMESTAMP '1899-12-30' + to_seconds(round(CAST("InvoiceDate" AS DOUBLE) * 86400))) AT TIME ZONE 'UTC' AS invoice_ts,
    CAST("Price" AS DECIMAL(12,3)) AS unit_price,
    CAST("Customer ID" AS INTEGER) AS customer_id,
    "Country" AS country,
    source_sheet,
    source_row
FROM bronze.online_retail_lines
WHERE NOT EXISTS (
    SELECT 1
    FROM silver.rejected_lines
    WHERE rejected_lines.source_sheet = online_retail_lines.source_sheet
        AND rejected_lines.source_row = online_retail_lines.source_row
)
