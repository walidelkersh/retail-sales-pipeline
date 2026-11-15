SELECT
    "Invoice" AS invoice_no,
    upper("Invoice") LIKE 'C%' AS is_cancellation,
    upper("StockCode") AS stock_code,
    trim("Description") AS description,
    CAST("Quantity" AS INTEGER) AS quantity,
    -- Excel serials carry float noise below a second.
    TIMESTAMP '1899-12-30' + to_seconds(round(CAST("InvoiceDate" AS DOUBLE) * 86400)) AS invoice_ts,
    CAST("Price" AS DECIMAL(12,3)) AS unit_price,
    CAST("Customer ID" AS INTEGER) AS customer_id,
    "Country" AS country,
    source_sheet,
    source_row
FROM bronze.online_retail_lines
