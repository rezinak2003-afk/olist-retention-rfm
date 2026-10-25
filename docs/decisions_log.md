# Decisions log

| Decision | Rule | Reason / caveat |
|---|---|---|
| Person-level key | `customer_unique_id` | `customer_id` is different for each order; using it would make repeat buying appear absent. |
| Order grain | Exactly one row per `order_id` | Payments are summed and reviews reduced to latest review before joining. |
| Status filter | Exclude `canceled`, `unavailable` from retention/RFM | Keeps those orders out of eligible purchase behaviour; other non-cancelled statuses remain. |
| Delivery subset | `order_status = delivered` and non-null actual delivery date | Delivery performance cannot be measured without actual delivery timestamp. |
| Late delivery | Actual delivered date later than estimated delivery date | Calendar-date comparison prevents same-day afternoon deliveries being labelled late. |
| Second-order metric | Second order at least 24 hours after first | Reduces same-day basket-splitting from the meaningful repeat measure. The broad 2+ orders RFM frequency still counts distinct eligible orders. |
| RFM snapshot | One day after latest eligible purchase in the dataset | Avoids using today's date and gives repeatable recency scoring. |
| Frequency score | Binary `Repeat` / `One-time` | Five frequency buckets would be dominated by one-time purchasers. |
| Cohort heatmap window | Jan 2017–Aug 2018 | Trims sparse early cohorts and later cohorts with limited observation time; full long-format cohort output is still exported. |
| Delivery statistics | Two-proportion z-test and CI for repeat; Mann–Whitney for review score; bootstrap CI for mean review difference | Results are associations, not causal effects. |
| Uplift scenarios | +1/+2/+3 percentage-point reactivation assumptions | Scenario model uses segment count × average historic spend × uplift, without margins/costs; not a forecast. |
