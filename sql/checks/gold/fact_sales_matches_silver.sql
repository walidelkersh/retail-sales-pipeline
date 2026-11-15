SELECT
    (SELECT count(*) FROM gold.fact_sales) AS fact_sales_count,
    (SELECT count(*) FROM silver.invoice_lines) AS invoice_lines_count
WHERE fact_sales_count <> invoice_lines_count
