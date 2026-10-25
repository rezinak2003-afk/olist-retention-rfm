-- Both values should match (allowing only rounding noise).
SELECT COUNT(*) AS rows,
       COUNT(DISTINCT order_id) AS distinct_orders,
       COUNT(*) - COUNT(DISTINCT order_id) AS duplicate_order_rows
FROM orders_enriched;

SELECT SUM(order_value) AS enriched_payment_value
FROM orders_enriched;

SELECT SUM(payment_value) AS source_payment_value_for_included_orders
FROM order_payments
WHERE order_id IN (SELECT order_id FROM orders_enriched);

SELECT COUNT(*) FILTER (WHERE review_score IS NULL) AS orders_without_review,
       COUNT(*) FILTER (WHERE delivered_ts IS NULL) AS orders_without_delivery_date,
       COUNT(*) FILTER (WHERE order_value IS NULL) AS orders_without_payment_value
FROM orders_enriched;
