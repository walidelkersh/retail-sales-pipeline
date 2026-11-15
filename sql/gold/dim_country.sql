SELECT
    row_number() OVER (ORDER BY retailer_name) AS country_key,
    retailer_name,
    alpha_2,
    alpha_3,
    iso_name,
    region,
    sub_region
FROM silver.countries
