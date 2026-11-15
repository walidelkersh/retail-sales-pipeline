SELECT *
FROM silver.invoice_lines
WHERE invoice_no IS NULL
    OR stock_code IS NULL
    OR quantity IS NULL
    OR invoice_ts IS NULL
    OR unit_price IS NULL
    OR country IS NULL
    OR source_sheet IS NULL
    OR source_row IS NULL
