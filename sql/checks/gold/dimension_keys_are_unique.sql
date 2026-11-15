SELECT
    'dim_country' AS dimension,
    country_key AS key
FROM gold.dim_country
GROUP BY country_key
HAVING count(*) > 1
UNION ALL
SELECT
    'dim_customer' AS dimension,
    customer_key AS key
FROM gold.dim_customer
GROUP BY customer_key
HAVING count(*) > 1
UNION ALL
SELECT
    'dim_date' AS dimension,
    date_key AS key
FROM gold.dim_date
GROUP BY date_key
HAVING count(*) > 1
UNION ALL
SELECT
    'dim_product' AS dimension,
    product_key AS key
FROM gold.dim_product
GROUP BY product_key
HAVING count(*) > 1
