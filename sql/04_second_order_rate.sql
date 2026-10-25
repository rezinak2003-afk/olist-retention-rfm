WITH ranked AS (
    SELECT customer_unique_id, purchase_ts,
           ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY purchase_ts, order_id) AS order_n
    FROM orders_enriched
),
firsts AS (
    SELECT customer_unique_id, purchase_ts AS first_ts
    FROM ranked WHERE order_n = 1
),
seconds AS (
    SELECT customer_unique_id, purchase_ts AS second_ts
    FROM ranked WHERE order_n = 2
)
SELECT DATE_TRUNC('month', f.first_ts) AS cohort_month,
       COUNT(*) AS eligible_customers,
       COUNT(*) FILTER (
           WHERE s.second_ts >= f.first_ts + INTERVAL 1 DAY
             AND s.second_ts <= f.first_ts + INTERVAL 90 DAY
       ) AS repeat_90d,
       COUNT(*) FILTER (
           WHERE s.second_ts >= f.first_ts + INTERVAL 1 DAY
             AND s.second_ts <= f.first_ts + INTERVAL 180 DAY
       ) AS repeat_180d
FROM firsts f
LEFT JOIN seconds s USING (customer_unique_id)
WHERE f.first_ts < TIMESTAMP '2018-03-01' -- full 180-day follow-up within dataset window
GROUP BY 1
ORDER BY 1;
