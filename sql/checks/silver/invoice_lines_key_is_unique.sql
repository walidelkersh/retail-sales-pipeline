SELECT source_sheet, source_row, count(*) AS line_count
FROM silver.invoice_lines
GROUP BY source_sheet, source_row
HAVING count(*) > 1
