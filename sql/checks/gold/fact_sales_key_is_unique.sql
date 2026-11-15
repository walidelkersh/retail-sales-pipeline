SELECT
    source_sheet,
    source_row,
    count(*) AS line_count
FROM gold.fact_sales
GROUP BY source_sheet, source_row
HAVING count(*) > 1
