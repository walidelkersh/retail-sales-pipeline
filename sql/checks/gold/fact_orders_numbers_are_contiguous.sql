SELECT customer_key
FROM gold.fact_orders
WHERE customer_order_number IS NOT NULL
GROUP BY customer_key
HAVING min(customer_order_number) <> 1
    OR max(customer_order_number) <> count(*)
    OR count(DISTINCT customer_order_number) <> count(*)
