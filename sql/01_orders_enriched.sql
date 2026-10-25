-- Grain: exactly one row per eligible order.
-- Aggregate payments and reviews before joining to prevent fan-out.

CREATE OR REPLACE TABLE order_value AS
SELECT order_id, SUM(TRY_CAST(payment_value AS DOUBLE)) AS order_value
FROM order_payments
GROUP BY order_id;

CREATE OR REPLACE TABLE order_review_latest AS
SELECT order_id, TRY_CAST(review_score AS INTEGER) AS review_score
FROM (
    SELECT order_id, review_score,
           ROW_NUMBER() OVER (
               PARTITION BY order_id
               ORDER BY TRY_CAST(review_answer_timestamp AS TIMESTAMP) DESC NULLS LAST
           ) AS rn
    FROM order_reviews
)
WHERE rn = 1;

CREATE OR REPLACE TABLE orders_enriched AS
WITH base AS (
    SELECT
        o.order_id,
        c.customer_unique_id,
        c.customer_state,
        o.order_status,
        TRY_CAST(o.order_purchase_timestamp AS TIMESTAMP) AS purchase_ts,
        TRY_CAST(o.order_delivered_customer_date AS TIMESTAMP) AS delivered_ts,
        TRY_CAST(o.order_estimated_delivery_date AS TIMESTAMP) AS estimated_ts,
        v.order_value,
        r.review_score
    FROM orders o
    JOIN customers c USING (customer_id)
    LEFT JOIN order_value v USING (order_id)
    LEFT JOIN order_review_latest r USING (order_id)
    WHERE LOWER(COALESCE(o.order_status, '')) NOT IN ('canceled', 'unavailable')
),
scored AS (
    SELECT *,
        DATE_DIFF('day', CAST(estimated_ts AS DATE), CAST(delivered_ts AS DATE)) AS days_vs_estimate
    FROM base
)
SELECT *,
       CASE WHEN days_vs_estimate IS NULL THEN NULL
            WHEN days_vs_estimate > 0 THEN 1 ELSE 0 END AS is_late
FROM scored;
