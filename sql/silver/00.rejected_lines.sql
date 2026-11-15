SELECT
    * EXCLUDE (ingested_at),
    CASE
        WHEN source_sheet = 'Year 2009-2010' AND "Invoice" IN (
            SELECT "Invoice"
            FROM bronze.online_retail_lines
            WHERE source_sheet = 'Year 2010-2011'
        ) THEN 'sheet_overlap'
        WHEN upper("Invoice") LIKE 'A%' THEN 'bad_debt_adjustment'
        WHEN upper("StockCode") LIKE 'TEST%' THEN 'test_stock_code'
        WHEN CAST("Price" AS DOUBLE) = 0 THEN 'unpriced_line'
        WHEN CAST("Quantity" AS INTEGER) < 0 AND upper("Invoice") NOT LIKE 'C%'
            THEN 'negative_quantity_without_cancellation'
    END AS reject_reason
FROM bronze.online_retail_lines
WHERE reject_reason IS NOT NULL
