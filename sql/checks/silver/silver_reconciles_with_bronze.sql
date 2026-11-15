SELECT
    (SELECT count(*) FROM bronze.online_retail_lines) AS bronze_count,
    (SELECT count(*) FROM silver.invoice_lines) AS invoice_lines_count,
    (SELECT count(*) FROM silver.rejected_lines) AS rejected_lines_count
WHERE bronze_count <> invoice_lines_count + rejected_lines_count
