WITH per_customer AS (
    SELECT customer_unique_id,
           COUNT(DISTINCT order_id) AS order_count,
           SUM(order_value) AS customer_revenue
    FROM orders_enriched
    GROUP BY customer_unique_id
)
SELECT COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE order_count >= 2) AS repeat_customers,
       ROUND(100.0 * COUNT(*) FILTER (WHERE order_count >= 2) / NULLIF(COUNT(*), 0), 2) AS repeat_pct,
       SUM(customer_revenue) AS total_revenue,
       SUM(customer_revenue) FILTER (WHERE order_count >= 2) AS repeat_customer_revenue,
       ROUND(100.0 * SUM(customer_revenue) FILTER (WHERE order_count >= 2) / NULLIF(SUM(customer_revenue), 0), 2) AS repeat_revenue_pct
FROM per_customer;
