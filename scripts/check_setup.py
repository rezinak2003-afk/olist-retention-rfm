#!/usr/bin/env python
"""Check that the expected Olist source files exist before analysis."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
REQUIRED = [
    "olist_customers_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
]
OPTIONAL = [
    "olist_order_items_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "product_category_name_translation.csv",
]
missing = [name for name in REQUIRED if not (RAW / name).exists()]
if missing:
    print("Missing required data files in data/raw/:")
    print("\n".join(f" - {name}" for name in missing))
    print("\nDownload the official Olist Kaggle archive and extract the CSVs directly into data/raw/.")
    raise SystemExit(1)
print("Required data files found:")
for name in REQUIRED:
    print(f" ✓ {name}")
not_found = [name for name in OPTIONAL if not (RAW / name).exists()]
if not_found:
    print("Optional files not found (core analysis can still run):")
    print("\n".join(f" - {name}" for name in not_found))
else:
    print("All optional source files are present.")
