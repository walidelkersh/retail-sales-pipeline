SELECT *
FROM silver.invoice_lines
WHERE unit_price <= 0
    OR quantity = 0
    OR (NOT is_cancellation AND quantity < 0)
    OR invoice_ts < TIMESTAMP '2009-12-01'
    OR invoice_ts >= TIMESTAMP '2011-12-10'
