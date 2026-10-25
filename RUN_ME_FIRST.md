# Run Project 2

1. Download the official archive from https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce and extract CSVs into `data/raw/`.
2. On Windows, open PowerShell in this folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\check_setup.py
.\.venv\Scripts\python.exe scripts\run_analysis.py
```

3. Inspect `data/processed/validation.json`, `docs/data_notes.md` and `docs/recommendation_memo.md` before using any metrics.
4. Build the Power BI file following `dashboard/POWER_BI_BUILD_SPEC.md`.
5. Do not commit `data/raw/`, the DuckDB database, `orders_enriched.csv` or `rfm_customers.csv`.
