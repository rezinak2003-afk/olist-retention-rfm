-- Run after scripts/run_analysis.py has loaded the raw tables into DuckDB.
-- Tables: customers, orders, order_items (optional), order_payments, order_reviews.

SELECT 'orders' AS table_name, COUNT(*) AS row_count FROM orders
UNION ALL SELECT 'customers', COUNT(*) FROM customers
UNION ALL SELECT 'order_payments', COUNT(*) FROM order_payments
UNION ALL SELECT 'order_reviews', COUNT(*) FROM order_reviews
ORDER BY table_name;

SELECT order_status, COUNT(*) AS orders
FROM orders
GROUP BY order_status
ORDER BY orders DESC;

SELECT MIN(TRY_CAST(order_purchase_timestamp AS TIMESTAMP)) AS first_purchase,
       MAX(TRY_CAST(order_purchase_timestamp AS TIMESTAMP)) AS last_purchase
FROM orders;

SELECT COUNT(*) AS review_rows,
       COUNT(DISTINCT order_id) AS orders_with_reviews,
       COUNT(*) - COUNT(DISTINCT order_id) AS extra_review_rows
FROM order_reviews;

SELECT COUNT(*) AS payment_rows,
       COUNT(DISTINCT order_id) AS orders_with_payments,
       COUNT(*) - COUNT(DISTINCT order_id) AS extra_payment_rows
FROM order_payments;

SELECT COUNT(*) AS customer_rows,
       COUNT(DISTINCT customer_unique_id) AS unique_customers
FROM customers;
