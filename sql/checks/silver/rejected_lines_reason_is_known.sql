SELECT *
FROM silver.rejected_lines
WHERE reject_reason IS NULL OR reject_reason NOT IN (
    'sheet_overlap',
    'bad_debt_adjustment',
    'test_stock_code',
    'unpriced_line',
    'negative_quantity_without_cancellation'
)
