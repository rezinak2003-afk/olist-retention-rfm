# Power BI dashboard build specification

Create `dashboard/olist_retention_rfm.pbix` locally in Power BI Desktop after running `scripts/run_analysis.py`. Use `data/processed/` as the source folder. Ensure date columns are typed as Date/DateTime and money columns as Decimal Number.

## Files to import

- `orders_enriched.csv` (local detail, one row per eligible order)
- `rfm_customers.csv` (one row per `customer_unique_id`)
- `cohort_retention.csv` (long format)
- `second_order_by_cohort.csv`
- `segment_summary.csv`
- `delay_summary.csv`
- `repeat_by_delivery.csv`

Suggested model relationships:

- `rfm_customers[customer_unique_id]` (one) → `orders_enriched[customer_unique_id]` (many), single-direction.
- Cohort and summary tables are aggregate visuals; do not directly join unrelated summaries in a way that multiplies rows. Use explicit measures or separate visuals.

## Page 1 — Executive Summary

Cards: eligible orders, unique customers, total payment value, repeat customer rate, meaningful 180-day second-order rate.

Visuals: eligible orders by purchase month; customer count vs repeat-customer share; text box with the run-specific recommendation and source period.

Finding-style title example: “Most eligible customers place one order — validate the highest-value re-engagement segment.” Replace it with the exact wording supported by generated outputs.

## Page 2 — Cohort Retention

- Matrix: rows = `cohort_month`; columns = `month_index`; values = `retention_rate`.
- Add background conditional formatting on retention rate.
- Line chart: `repeat_rate_90d` and `repeat_rate_180d` by cohort month from `second_order_by_cohort.csv`.
- Footer: cohorts after Aug 2018 have insufficient follow-up for the default heatmap; the meaningful second-purchase definition excludes orders <24 hours after first purchase.

## Page 3 — RFM Segments

- Bar chart: revenue by `segment`.
- Bar chart: number of customers by segment.
- Table: segment, customers, customer share, revenue share, average spend/customer, average days since last order, average review, +1/+2/+3pp scenario value, and priority score.
- Call out the selected segment as a **screening candidate**, not a machine-learned propensity prediction.

## Page 4 — Delivery & Reviews

- Column chart: average review score by delivery-delay bucket.
- Column chart: 180-day repeat rate by first-order delivery group with 95% CI fields.
- Text box: difference in repeat rate (late minus on-time/early), 95% CI and p-value; mean review-score difference with bootstrap CI and Mann–Whitney p-value.
- Footer: observational association only; potential confounders include state, seller, product category and order value.

## Suggested DAX measures

```DAX
Total Revenue = SUM(orders_enriched[order_value])

Orders = DISTINCTCOUNT(orders_enriched[order_id])

Customers = DISTINCTCOUNT(rfm_customers[customer_unique_id])

Repeat Customers =
    CALCULATE(
        DISTINCTCOUNT(rfm_customers[customer_unique_id]),
        rfm_customers[frequency] >= 2
    )

Repeat Customer Rate = DIVIDE([Repeat Customers], [Customers])
```

## Publish / portfolio evidence

Save the `.pbix` in `dashboard/` and place 4 page screenshots under `docs/screenshots/`. If Power BI Service public publishing is unavailable, commit the screenshot evidence and include a PDF export. Do not upload raw data; check the dataset's non-commercial/share-alike terms before redistributing any derivative tables.
