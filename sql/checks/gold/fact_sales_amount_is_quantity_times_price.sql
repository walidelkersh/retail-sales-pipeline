SELECT *
FROM gold.fact_sales
WHERE line_amount IS DISTINCT FROM quantity * unit_price
