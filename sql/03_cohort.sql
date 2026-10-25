WITH first_orders AS (
    SELECT customer_unique_id,
           DATE_TRUNC('month', MIN(purchase_ts)) AS cohort_month
    FROM orders_enriched
    GROUP BY customer_unique_id
),
activity AS (
    SELECT DISTINCT e.customer_unique_id,
           f.cohort_month,
           DATE_DIFF('month', f.cohort_month, DATE_TRUNC('month', e.purchase_ts)) AS month_index
    FROM orders_enriched e
    JOIN first_orders f USING (customer_unique_id)
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(DISTINCT customer_unique_id) AS cohort_customers
    FROM first_orders
    GROUP BY cohort_month
),
active AS (
    SELECT cohort_month, month_index, COUNT(DISTINCT customer_unique_id) AS active_customers
    FROM activity
    GROUP BY cohort_month, month_index
)
SELECT a.cohort_month, a.month_index, a.active_customers, s.cohort_customers,
       a.active_customers * 1.0 / NULLIF(s.cohort_customers, 0) AS retention_rate
FROM active a
JOIN cohort_sizes s USING (cohort_month)
ORDER BY a.cohort_month, a.month_index;
