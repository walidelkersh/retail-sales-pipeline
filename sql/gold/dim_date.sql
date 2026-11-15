WITH invoice_range AS (
    SELECT
        CAST(min(invoice_ts) AS DATE) AS first_date,
        CAST(max(invoice_ts) AS DATE) AS last_date
    FROM silver.invoice_lines
), calendar AS (
    SELECT CAST(day AS DATE) AS date
    FROM invoice_range,
        LATERAL generate_series(first_date, last_date, INTERVAL 1 DAY) AS days(day)
)
SELECT
    CAST(strftime(date, '%Y%m%d') AS INTEGER) AS date_key,
    date,
    year(date) AS year,
    quarter(date) AS quarter,
    month(date) AS month,
    monthname(date) AS month_name,
    isodow(date) AS day_of_week,
    dayname(date) AS day_name,
    isodow(date) IN (6, 7) AS is_weekend
FROM calendar
