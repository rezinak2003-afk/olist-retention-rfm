# Recommendation memo: Olist customer retention and RFM

**Decision:** use the dataset-derived segment score as a screening recommendation, then validate it with a controlled retention test. The results are descriptive and cannot establish causality.

## Headline

- Eligible customers: **94,990** across **98,207 eligible orders**.
- Customers with 2+ eligible orders: **2,888 (3.04%)**.
- Eligible payment value: **R$ 15,739,137.01**; share from repeat customers: **5.66%**.
- Second order at least 24 hours after the first within 90 days: **1,005/82,765 (1.21%)** among customers with sufficient follow-up.
- Same meaningful second-order rule within 180 days: **1,069/56,630 (1.89%)** among customers with sufficient follow-up.

## Candidate segment to test first

**New high-value** ranked highest under the explicit screening score (30% customer-size percentile, 30% average-spend percentile, 20% recency/reachability percentile, 20% lower-review/service-signal percentile). This is a decision aid, not a validated propensity model.
- Customers: 14,647 (15.42% of customers)
- Historical revenue: R$ 4,439,321.05 (28.21% of eligible revenue)
- Average historical spend per customer: R$ 303.09
- Average days since last purchase: 97.7
- Average associated review score: 4.09
- Assumed extra revenue at +1/+2/+3 percentage-point reactivation uplift: R$ 44,393.21 / R$ 88,786.42 / R$ 133,179.63.
- These uplift amounts are scenario values calculated using historical average spend per customer; they are not a forecast, margin estimate, or incremental value proven by an experiment.

## Delivery and review evidence

- First-order 180-day repeat rate, late delivery: 1.47% (54/3,670; 95% Wilson CI 1.13%–1.91%).
- First-order 180-day repeat rate, on-time/early delivery: 1.93% (998/51,821; 95% Wilson CI 1.81%–2.05%).
- Difference in repeat rate (late minus on-time/early): -0.45%; 95% CI -0.82% to 0.00%; two-proportion z-test p = 0.05107.
- Mean review-score difference (late minus on-time/early): -2.020 points; bootstrap 95% CI -2.058 to -1.981; Mann–Whitney p = 0.

### Average review by delivery bucket

| Delivery bucket | Orders | Average review | 1–2 star share |
|---|---:|---:|---:|
| On time or early | 89,936 | 4.29 | 9.27% |
| 1-3 days late | 1,870 | 3.29 | 32.13% |
| 4-7 days late | 1,802 | 2.10 | 67.68% |
| 8+ days late | 2,862 | 1.70 | 79.29% |

## Action

1. Test a low-cost segment-specific re-engagement message or second-purchase offer; keep a random holdout and measure incremental 90/180-day repeat purchases and contribution margin before scaling.
2. If delivered-late customers show materially worse reviews, test a proactive service-recovery message for late deliveries and track review/repeat outcomes separately.
3. Review segment size, reachability, and service evidence jointly before choosing a campaign. Include contactability and campaign cost in the next iteration.

## Limitations

- Historical, anonymised Olist marketplace data from 2016–2018; one market and not current live-store performance.
- Customers are identified using `customer_unique_id`; `customer_id` is order-specific and is not suitable as a person-level repeat key.
- Payment and review tables are aggregated before joining. Validation checks enforce one row per eligible order and reconcile payment value.
- Same-day or sub-24-hour second orders are excluded from meaningful 90/180-day second-order metrics, but still count toward RFM frequency and the broad 2+ order statistic.
- Delivery/review and delivery/repeat comparisons are observational. State, seller, category, order value, and other factors can confound the relationships.
- Revenue uplift cases are explicit assumptions and exclude margin, incentive costs, contactability, and cannibalisation.

## Recommended decision

Proceed to a controlled re-engagement test for the selected segment only after campaign costs, channel eligibility, and the holdout design are defined. Do not describe these observational results as proof that delivery delay causes churn.
