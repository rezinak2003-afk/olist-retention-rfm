SELECT CASE
           WHEN days_vs_estimate IS NULL THEN 'Unknown delivery date'
           WHEN days_vs_estimate <= 0 THEN 'On time or early'
           WHEN days_vs_estimate <= 3 THEN '1-3 days late'
           WHEN days_vs_estimate <= 7 THEN '4-7 days late'
           ELSE '8+ days late'
       END AS delay_bucket,
       COUNT(*) AS orders,
       AVG(review_score) AS avg_review_score,
       AVG(CASE WHEN review_score <= 2 THEN 1.0 ELSE 0.0 END) AS pct_1_2_star,
       AVG(days_vs_estimate) AS mean_days_vs_estimate
FROM orders_enriched
WHERE LOWER(order_status) = 'delivered' AND delivered_ts IS NOT NULL
GROUP BY 1
ORDER BY CASE delay_bucket
             WHEN 'On time or early' THEN 1
             WHEN '1-3 days late' THEN 2
             WHEN '4-7 days late' THEN 3
             WHEN '8+ days late' THEN 4 ELSE 5 END;
