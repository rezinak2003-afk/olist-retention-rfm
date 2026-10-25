# Olist Customer Retention & RFM Analysis

**Project question:** Which customer segment should an e-commerce business prioritise for retention or re-engagement, and is delivery performance associated with repeat buying?

**Stack:** DuckDB SQL, Python, pandas, NumPy, SciPy, statsmodels, matplotlib, Power BI, GitHub.

> **Data/results integrity:** This repository contains the analysis code and documentation, not the licensed raw Olist data. Download the dataset from its official Kaggle page, run the pipeline locally, and use the generated real outputs to populate your portfolio. No findings or effect sizes are hard-coded. The script writes a result-specific recommendation memo only after running on the actual source files.

## Data source

[ Brazilian E-Commerce Public Dataset by Olist — Kaggle ](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)  
The dataset covers roughly 100,000 orders from 2016–2018. Kaggle lists the dataset under **CC BY-NC-SA 4.0**. Check the current terms before redistribution or commercial use. Do not commit raw data to this repository.

## Run it

For a compact run sheet, see [`RUN_ME_FIRST.md`](RUN_ME_FIRST.md).

### 1. Download and place the data

Download the Kaggle ZIP and extract the CSVs directly into `data/raw/`. At minimum, these four files are needed:

- `olist_customers_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`

The official archive also includes order items, products, sellers, geolocation and product-category translation files. The pipeline profiles any of these optional files when present.

### 2. Create the environment (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Verify source files and run all analyses

```powershell
.\.venv\Scripts\python.exe scripts\check_setup.py
.\.venv\Scripts\python.exe scripts\run_analysis.py
```

The run performs profiling, loads the core tables into local DuckDB, creates `orders_enriched`, enforces one row per order and reconciles payment totals, then computes repeat purchasing, cohorts, RFM segments, delay/review associations, confidence intervals and scenario estimates.

## Key output files

Generated under `data/processed/`:

- `orders_enriched.csv` — one row per eligible order for local Power BI analysis; excluded from Git by `.gitignore`.
- `rfm_customers.csv` — customer-level RFM scores and segments; excluded from Git by `.gitignore`.
- `repeat_metrics.csv` — overall repeat-customer metrics.
- `second_order_by_cohort.csv` — 90- and 180-day second-purchase rates by first-purchase cohort.
- `cohort_retention.csv` — long-format cohort/month-index retention data.
- `segment_summary.csv` — customers, revenue, recency, average spend, reviews and priority scoring by RFM segment.
- `delay_summary.csv` — review and low-rating summaries by delivery-delay bucket.
- `repeat_by_delivery.csv` — 180-day repeat rate by first-order delivery status with 95% Wilson intervals.
- `analysis_summary.json` and `validation.json` — run-specific metrics and validation results.

Generated documentation and visuals:

- `docs/data_notes.md` — actual row counts, join-grain checks, payment reconciliation and analysis decisions.
- `docs/recommendation_memo.md` — data-driven memo populated by the run.
- `docs/figures/cohort_heatmap.png`
- `docs/figures/segment_revenue.png`
- `docs/figures/review_by_delivery_delay.png`
- `docs/figures/repeat_rate_by_delivery.png`

The small aggregate tables can be reviewed and committed after checking the dataset licence. Do not commit customer-level or raw data.

## Analysis definitions

- **Person-level customer key:** `customer_unique_id`, because `customer_id` is assigned per order.
- **Eligible orders:** all statuses except `canceled` and `unavailable` for retention/RFM; delivery analyses use `delivered` orders with an actual delivery date.
- **Order value:** payment rows are summed to one row per order before joining. Item rows are not joined into the order-grain table, preventing revenue fan-out.
- **Review:** latest review answer timestamp per order.
- **Late delivery:** delivered calendar date after estimated delivery calendar date; same-day afternoon deliveries are not late.
- **RFM snapshot:** one day after the last eligible purchase in the dataset, not the current date.
- **Frequency:** binary Repeat (2+ eligible orders) / One-time, because frequency quintiles are not useful when one-time customers dominate.
- **Meaningful 90/180-day second purchase:** second eligible order occurs at least 24 hours after the first and within the selected window; this reduces same-day basket-split inflation.
- **Cohorts:** monthly first-purchase month; late cohorts have limited follow-up (right-censoring), so the default heatmap shows Jan 2017–Aug 2018.
- **Uplift scenarios:** +1, +2 and +3 percentage-point reactivation assumptions. These are scenario estimates, not forecasts; they do not include margin, campaign costs or contactability.

## Tests

After installing requirements, run the small synthetic logic tests with `python -m pytest -q tests/`. These tests only check code paths; their small artificial rows are never used as project results.

## Power BI

Follow [`dashboard/POWER_BI_BUILD_SPEC.md`](dashboard/POWER_BI_BUILD_SPEC.md) after running the pipeline. The four report pages are Executive Summary, Cohort Retention, RFM Segments, and Delivery & Reviews. A `.pbix` file is not included because it must be created in Power BI Desktop from your locally generated data.

## Repository structure

```text
olist-retention-rfm/
├── data/raw/                 # local-only Kaggle CSVs; ignored by Git
├── data/processed/           # output tables; row-level files ignored by Git
├── sql/                      # numbered DuckDB SQL scripts
├── src/olist_analysis.py     # complete analysis pipeline
├── scripts/                  # setup check and runner
├── notebooks/                # Jupyter walkthrough
├── dashboard/                # Power BI report specification
└── docs/                     # data notes, decision log, generated memo and figures
```

## Limitations

This is historical, anonymised 2016–2018 marketplace data, not current live business performance. Repeat and delivery findings are observational; differences may be confounded by state, seller, category, value or customer mix. Scenario uplifts are explicit assumptions. Treat statistical significance separately from business importance.

## License and attribution

Analysis code in this repository is licensed under MIT. The Olist source data remains subject to its own CC BY-NC-SA 4.0 terms and is not redistributed here. Attribution: Olist, *Brazilian E-Commerce Public Dataset by Olist*, Kaggle.
