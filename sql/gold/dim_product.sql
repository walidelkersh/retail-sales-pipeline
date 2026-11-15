WITH descriptions AS (
    SELECT
        stock_code,
        description
    FROM silver.invoice_lines
    GROUP BY stock_code, description
    QUALIFY row_number() OVER (
        PARTITION BY stock_code
        ORDER BY description IS NULL, count(*) DESC, description
    ) = 1
)
SELECT
    row_number() OVER (ORDER BY stock_code) AS product_key,
    stock_code,
    description,
    regexp_matches(stock_code, '^[0-9]{5}') AS is_merchandise
FROM descriptions
