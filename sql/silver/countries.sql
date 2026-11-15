SELECT
    country_names.retailer_name,
    country_names.alpha_2,
    country_codes."alpha-3" AS alpha_3,
    country_codes.name AS iso_name,
    CASE
        WHEN country_names.alpha_2 IS NULL THEN country_names.fallback_region
        ELSE country_codes.region
    END AS region,
    country_codes."sub-region" AS sub_region
FROM bronze.country_names
LEFT JOIN bronze.country_codes
    ON country_names.alpha_2 = country_codes."alpha-2"
