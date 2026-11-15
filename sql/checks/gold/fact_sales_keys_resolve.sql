SELECT *
FROM gold.fact_sales AS sales
WHERE date_key IS NULL
    OR product_key IS NULL
    OR customer_key IS NULL
    OR country_key IS NULL
    OR NOT EXISTS (
        SELECT 1 FROM gold.dim_date WHERE date_key = sales.date_key
    )
    OR NOT EXISTS (
        SELECT 1 FROM gold.dim_product WHERE product_key = sales.product_key
    )
    OR NOT EXISTS (
        SELECT 1 FROM gold.dim_customer WHERE customer_key = sales.customer_key
    )
    OR NOT EXISTS (
        SELECT 1 FROM gold.dim_country WHERE country_key = sales.country_key
    )
