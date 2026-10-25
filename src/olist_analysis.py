from __future__ import annotations

import json
import math
import re
import sys
import warnings
from pathlib import Path
from typing import Any

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
DOCS = ROOT / "docs"
FIGURES = DOCS / "figures"
DB_PATH = ROOT / "olist.duckdb"

REQUIRED_FILES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
}
OPTIONAL_FILES = {
    "order_items": "olist_order_items_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "product_category_translation": "product_category_name_translation.csv",
}


def _csv_path_sql(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _ensure_columns(df: pd.DataFrame, required: set[str], filename: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{filename} is missing required columns: {', '.join(missing)}")


def _load_tables(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    missing = [filename for filename in REQUIRED_FILES.values() if not (RAW / filename).exists()]
    if missing:
        expected = "\n".join(f"  - {f}" for f in missing)
        raise FileNotFoundError(
            "Required Olist CSV files were not found in data/raw/.\n"
            f"Missing:\n{expected}\n\n"
            "Download the official Kaggle archive, extract the CSV files, and put them directly in data/raw/."
        )

    counts: dict[str, int] = {}
    for table, filename in REQUIRED_FILES.items():
        path = RAW / filename
        if table == "order_reviews":
            # pandas handles the CSV's free-text columns; only load fields used downstream.
            review_df = pd.read_csv(
                path,
                usecols=lambda c: c in {"order_id", "review_score", "review_answer_timestamp"},
                low_memory=False,
            )
            _ensure_columns(review_df, {"order_id", "review_score", "review_answer_timestamp"}, filename)
            review_df["order_id"] = review_df["order_id"].astype("string")
            con.register("_reviews_df", review_df)
            con.execute("CREATE OR REPLACE TABLE order_reviews AS SELECT * FROM _reviews_df")
            con.unregister("_reviews_df")
        else:
            p = _csv_path_sql(path)
            con.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT * FROM read_csv_auto('{p}', header=true, sample_size=-1, ignore_errors=false)"
            )
        counts[table] = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchall()[0][0])

    # Optional tables are profiled if present; they are not required for the core analysis.
    for table, filename in OPTIONAL_FILES.items():
        path = RAW / filename
        if path.exists():
            p = _csv_path_sql(path)
            con.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT * FROM read_csv_auto('{p}', header=true, sample_size=10000, ignore_errors=true)"
            )
            counts[table] = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchall()[0][0])
    return counts


def _run_sql_file(con: duckdb.DuckDBPyConnection, name: str) -> None:
    sql = (ROOT / "sql" / name).read_text(encoding="utf-8")
    con.execute(sql)


def _profile_and_validate(con: duckdb.DuckDBPyConnection, counts: dict[str, int]) -> dict[str, Any]:
    status = con.execute(
        "SELECT order_status, COUNT(*) AS orders FROM orders GROUP BY order_status ORDER BY orders DESC"
    ).df()
    date_bounds = con.execute(
        "SELECT MIN(TRY_CAST(order_purchase_timestamp AS TIMESTAMP)) AS first_purchase, "
        "MAX(TRY_CAST(order_purchase_timestamp AS TIMESTAMP)) AS last_purchase FROM orders"
    ).df().iloc[0].to_dict()
    duplicate_diagnostics = con.execute(
        "SELECT (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM order_reviews) AS extra_review_rows, "
        "(SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM order_payments) AS extra_payment_rows, "
        "(SELECT COUNT(*) - COUNT(DISTINCT customer_unique_id) FROM customers) AS extra_customer_identity_rows"
    ).df().iloc[0].to_dict()
    _run_sql_file(con, "01_orders_enriched.sql")
    validation = con.execute(
        "SELECT COUNT(*) AS rows, COUNT(DISTINCT order_id) AS distinct_orders, "
        "COUNT(*) - COUNT(DISTINCT order_id) AS duplicate_order_rows, "
        "COUNT(*) FILTER (WHERE review_score IS NULL) AS orders_without_review, "
        "COUNT(*) FILTER (WHERE delivered_ts IS NULL) AS orders_without_delivery_date, "
        "COUNT(*) FILTER (WHERE order_value IS NULL) AS orders_without_payment_value "
        "FROM orders_enriched"
    ).df().iloc[0].to_dict()
    revenue_check = con.execute(
        "SELECT (SELECT SUM(order_value) FROM orders_enriched) AS enriched_payment_value, "
        "(SELECT SUM(payment_value) FROM order_payments "
        " WHERE order_id IN (SELECT order_id FROM orders_enriched)) AS source_payment_value"
    ).df().iloc[0].to_dict()
    for key, value in {**validation, **revenue_check, **duplicate_diagnostics, **date_bounds}.items():
        if pd.isna(value):
            if key in {"first_purchase", "last_purchase"}:
                continue
        if isinstance(value, (np.integer,)):
            value = int(value)
    rows = int(validation["rows"])
    distinct_orders = int(validation["distinct_orders"])
    if rows != distinct_orders:
        raise AssertionError(f"orders_enriched is not one row per order: {rows} rows vs {distinct_orders} distinct IDs")
    a = float(revenue_check["enriched_payment_value"] or 0)
    b = float(revenue_check["source_payment_value"] or 0)
    if not math.isclose(a, b, rel_tol=1e-8, abs_tol=0.02):
        raise AssertionError(f"Payment reconciliation failed: enriched={a:.2f}, source={b:.2f}")

    # JSON-safe types
    summary = {
        "raw_table_row_counts": counts,
        "orders_status_counts": status.to_dict(orient="records"),
        "source_date_min": pd.Timestamp(date_bounds["first_purchase"]).isoformat() if pd.notna(date_bounds["first_purchase"]) else None,
        "source_date_max": pd.Timestamp(date_bounds["last_purchase"]).isoformat() if pd.notna(date_bounds["last_purchase"]) else None,
        "duplicate_diagnostics": {k: int(v) for k, v in duplicate_diagnostics.items()},
        "validation": {k: int(v) for k, v in validation.items()},
        "revenue_reconciliation": {k: float(v) if pd.notna(v) else None for k, v in revenue_check.items()},
    }
    return summary


def _build_repeat_and_cohorts(orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    x = orders.copy()
    x["purchase_ts"] = pd.to_datetime(x["purchase_ts"], errors="coerce")
    x["order_value"] = pd.to_numeric(x["order_value"], errors="coerce")
    x = x.dropna(subset=["customer_unique_id", "purchase_ts", "order_id"])
    x["customer_unique_id"] = x["customer_unique_id"].astype(str)
    x = x.sort_values(["customer_unique_id", "purchase_ts", "order_id"])

    per_customer = x.groupby("customer_unique_id", as_index=False).agg(
        order_count=("order_id", "nunique"),
        customer_revenue=("order_value", "sum"),
        first_purchase=("purchase_ts", "min"),
        last_purchase=("purchase_ts", "max"),
    )
    repeat_customers = int((per_customer["order_count"] >= 2).sum())
    customer_count = int(len(per_customer))
    total_revenue = float(per_customer["customer_revenue"].sum())
    repeat_revenue = float(per_customer.loc[per_customer.order_count >= 2, "customer_revenue"].sum())
    headline = {
        "customers": customer_count,
        "repeat_customers": repeat_customers,
        "repeat_pct": (100 * repeat_customers / customer_count) if customer_count else None,
        "eligible_orders": int(x.order_id.nunique()),
        "total_revenue": total_revenue,
        "repeat_customer_revenue": repeat_revenue,
        "repeat_revenue_pct": (100 * repeat_revenue / total_revenue) if total_revenue else None,
    }
    repeat_metrics = pd.DataFrame([headline])

    # All customers' first and second eligible orders. To avoid counting basket-split orders,
    # 90/180-day return metrics require the second order to be at least 24 hours later.
    x["order_n"] = x.groupby("customer_unique_id").cumcount() + 1
    firsts = x[x.order_n == 1][["customer_unique_id", "purchase_ts"]].rename(columns={"purchase_ts": "first_ts"})
    seconds = x[x.order_n == 2][["customer_unique_id", "purchase_ts"]].rename(columns={"purchase_ts": "second_ts"})
    firsts = firsts.merge(seconds, on="customer_unique_id", how="left")
    gap = firsts["second_ts"] - firsts["first_ts"]
    firsts["eligible_90d"] = firsts["first_ts"] < pd.Timestamp("2018-07-01")
    firsts["eligible_180d"] = firsts["first_ts"] < pd.Timestamp("2018-03-01")
    firsts["repeat_90d"] = gap.ge(pd.Timedelta(days=1)) & gap.le(pd.Timedelta(days=90))
    firsts["repeat_180d"] = gap.ge(pd.Timedelta(days=1)) & gap.le(pd.Timedelta(days=180))
    firsts["cohort_month"] = firsts["first_ts"].dt.to_period("M").dt.to_timestamp()
    second_order_rows = []
    for cohort, g in firsts.groupby("cohort_month", dropna=True):
        g90 = g[g.eligible_90d]
        g180 = g[g.eligible_180d]
        second_order_rows.append({
            "cohort_month": cohort,
            "eligible_customers_90d": int(len(g90)),
            "repeat_90d": int(g90.repeat_90d.sum()),
            "repeat_rate_90d": float(g90.repeat_90d.mean()) if len(g90) else np.nan,
            "eligible_customers_180d": int(len(g180)),
            "repeat_180d": int(g180.repeat_180d.sum()),
            "repeat_rate_180d": float(g180.repeat_180d.mean()) if len(g180) else np.nan,
        })
    second_by_cohort = pd.DataFrame(second_order_rows).sort_values("cohort_month")

    first_cohort = x.groupby("customer_unique_id", as_index=False)["purchase_ts"].min().rename(columns={"purchase_ts": "cohort_month"})
    first_cohort["cohort_month"] = first_cohort["cohort_month"].dt.to_period("M").dt.to_timestamp()
    activity = x[["customer_unique_id", "purchase_ts"]].copy()
    activity["activity_month"] = activity["purchase_ts"].dt.to_period("M").dt.to_timestamp()
    activity = activity.merge(first_cohort, on="customer_unique_id", how="left")
    activity["month_index"] = (
        (activity["activity_month"].dt.year - activity["cohort_month"].dt.year) * 12
        + activity["activity_month"].dt.month - activity["cohort_month"].dt.month
    )
    activity = activity.drop_duplicates(["customer_unique_id", "cohort_month", "month_index"])
    cohort_sizes = first_cohort.groupby("cohort_month")["customer_unique_id"].nunique().rename("cohort_customers")
    active = activity.groupby(["cohort_month", "month_index"])["customer_unique_id"].nunique().rename("active_customers")
    cohort = active.reset_index().merge(cohort_sizes.reset_index(), on="cohort_month", how="left")
    cohort["retention_rate"] = cohort["active_customers"] / cohort["cohort_customers"]
    cohort = cohort.sort_values(["cohort_month", "month_index"])
    return repeat_metrics, second_by_cohort, cohort, {"headline": headline, "firsts": firsts}


def _build_rfm(orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    x = orders.copy()
    x["purchase_ts"] = pd.to_datetime(x["purchase_ts"], errors="coerce")
    x["order_value"] = pd.to_numeric(x["order_value"], errors="coerce").fillna(0)
    x = x.dropna(subset=["customer_unique_id", "purchase_ts"])
    x["customer_unique_id"] = x["customer_unique_id"].astype(str)
    snapshot = x["purchase_ts"].max().normalize() + pd.Timedelta(days=1)
    rfm = x.groupby("customer_unique_id", as_index=False).agg(
        last_purchase=("purchase_ts", "max"),
        frequency=("order_id", "nunique"),
        monetary=("order_value", "sum"),
        avg_review=("review_score", "mean"),
        customer_state=("customer_state", "last"),
    )
    rfm["recency"] = (snapshot - rfm["last_purchase"].dt.normalize()).dt.days
    if len(rfm) < 5:
        raise ValueError("At least five unique customers are needed to produce quintile RFM scores.")
    # Rank before qcut so ties in monetary values and recency don't collapse the bins.
    rfm["R"] = pd.qcut(rfm["recency"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    rfm["M"] = pd.qcut(rfm["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["F"] = np.where(rfm["frequency"] >= 2, "Repeat", "One-time")
    conditions = [
        (rfm.F == "Repeat") & (rfm.R >= 3),
        (rfm.F == "Repeat") & (rfm.R < 3),
        (rfm.F == "One-time") & (rfm.R >= 4) & (rfm.M >= 4),
        (rfm.F == "One-time") & (rfm.R >= 4),
        (rfm.F == "One-time") & (rfm.R <= 3) & (rfm.M >= 4),
    ]
    names = ["Active repeat buyers", "Lapsed repeat buyers", "New high-value",
             "New lower-value", "At-risk high-value (one-time)"]
    rfm["segment"] = np.select(conditions, names, default="Lost lower-value (one-time)")
    total_rev = float(rfm.monetary.sum())
    seg = rfm.groupby("segment", as_index=False).agg(
        customers=("customer_unique_id", "nunique"),
        revenue=("monetary", "sum"),
        avg_spend_per_customer=("monetary", "mean"),
        avg_days_since_last_order=("recency", "mean"),
        avg_review=("avg_review", "mean"),
    )
    total_cust = int(rfm.customer_unique_id.nunique())
    seg["pct_customers"] = seg["customers"] / total_cust if total_cust else 0
    seg["pct_revenue"] = seg["revenue"] / total_rev if total_rev else 0
    # Guide-defined scenario: segment size * average historical spend * assumed incremental reactivation.
    for pp in (1, 2, 3):
        seg[f"revenue_at_{pp}pp_uplift"] = seg["customers"] * seg["avg_spend_per_customer"] * pp / 100
    # Transparent rule-based screening score: size 30%, spend 30%, recency/reachability 20%, review signal 20%.
    def percentile(s: pd.Series, high_is_good: bool = True) -> pd.Series:
        return s.rank(pct=True, ascending=high_is_good, method="average").fillna(0.5)
    seg["size_score"] = percentile(seg["pct_customers"])
    seg["value_score"] = percentile(seg["avg_spend_per_customer"])
    seg["reachability_score"] = percentile(seg["avg_days_since_last_order"], high_is_good=False)
    # Lower average review is treated as more potential service friction, not proof of fixability.
    seg["service_signal_score"] = percentile(seg["avg_review"], high_is_good=False)
    seg["priority_score"] = (
        0.30 * seg["size_score"] + 0.30 * seg["value_score"]
        + 0.20 * seg["reachability_score"] + 0.20 * seg["service_signal_score"]
    )
    seg = seg.sort_values(["priority_score", "revenue_at_2pp_uplift"], ascending=False)
    rfm["snapshot_date"] = snapshot
    summary = {
        "snapshot_date": snapshot.date().isoformat(),
        "segment_priority_rule": "30% customer-size percentile + 30% average-spend percentile + 20% reachability (lower recency) + 20% service signal (lower average review); screening heuristic, not causal model",
        "recommended_segment": str(seg.iloc[0]["segment"]) if not seg.empty else None,
    }
    return rfm, seg, summary


def _bootstrap_mean_diff(late: np.ndarray, ontime: np.ndarray, seed: int = 42, reps: int = 1000) -> tuple[float, float]:
    late = late[~np.isnan(late)]
    ontime = ontime[~np.isnan(ontime)]
    if not len(late) or not len(ontime):
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    diffs = np.empty(reps)
    for i in range(reps):
        diffs[i] = rng.choice(late, size=len(late), replace=True).mean() - rng.choice(ontime, size=len(ontime), replace=True).mean()
    return float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))


def _build_delivery_analysis(orders: pd.DataFrame, firsts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    x = orders.copy()
    x["purchase_ts"] = pd.to_datetime(x["purchase_ts"], errors="coerce")
    x["delivered_ts"] = pd.to_datetime(x["delivered_ts"], errors="coerce")
    x["estimated_ts"] = pd.to_datetime(x["estimated_ts"], errors="coerce")
    x["review_score"] = pd.to_numeric(x["review_score"], errors="coerce")
    x["days_vs_estimate"] = pd.to_numeric(x["days_vs_estimate"], errors="coerce")
    d = x[(x.order_status.astype(str).str.lower() == "delivered") & x.delivered_ts.notna() & x.days_vs_estimate.notna()].copy()
    d["delay_bucket"] = pd.cut(
        d["days_vs_estimate"], bins=[-np.inf, 0, 3, 7, np.inf],
        labels=["On time or early", "1-3 days late", "4-7 days late", "8+ days late"],
        right=True,
    )
    delay_summary = d.groupby("delay_bucket", observed=False).agg(
        orders=("order_id", "nunique"),
        avg_review_score=("review_score", "mean"),
        pct_1_2_star=("review_score", lambda s: float((s <= 2).mean()) if s.notna().any() else np.nan),
        mean_days_vs_estimate=("days_vs_estimate", "mean"),
        median_days_vs_estimate=("days_vs_estimate", "median"),
    ).reset_index()
    delay_summary["delay_bucket"] = delay_summary["delay_bucket"].astype(str)

    # firsts contains one row per customer's first eligible order plus second_ts and repeat outcomes.
    ranked = x.sort_values(["customer_unique_id", "purchase_ts", "order_id"]).copy()
    ranked["order_n"] = ranked.groupby("customer_unique_id").cumcount() + 1
    first_orders = ranked[ranked.order_n == 1].copy()
    second_orders = ranked.loc[ranked.order_n == 2, ["customer_unique_id", "purchase_ts"]].rename(columns={"purchase_ts": "second_ts"})
    first_orders = first_orders.merge(second_orders, on="customer_unique_id", how="left")
    gap = first_orders["second_ts"] - first_orders["purchase_ts"]
    first_orders["repeat_180d"] = gap.ge(pd.Timedelta(days=1)) & gap.le(pd.Timedelta(days=180))
    first_orders = first_orders[
        (first_orders.order_status.astype(str).str.lower() == "delivered")
        & first_orders.delivered_ts.notna()
        & (first_orders.purchase_ts < pd.Timestamp("2018-03-01"))
        & first_orders.days_vs_estimate.notna()
    ].copy()
    first_orders["delivery_group"] = np.where(first_orders["days_vs_estimate"] > 0, "Late", "On time or early")
    repeat_rows = []
    stats: dict[str, Any] = {}
    for group in ["Late", "On time or early"]:
        g = first_orders[first_orders.delivery_group == group]
        n = int(len(g))
        k = int(g.repeat_180d.sum())
        rate = k / n if n else np.nan
        if n:
            low, high = (float(v) for v in __import__("statsmodels.stats.proportion", fromlist=["proportion_confint"]).proportion_confint(k, n, alpha=0.05, method="wilson"))
        else:
            low = high = np.nan
        repeat_rows.append({"delivery_group": group, "eligible_first_orders": n, "repeat_180d_customers": k,
                            "repeat_rate_180d": rate, "ci95_low": low, "ci95_high": high})
        stats[group] = {"n": n, "repeat_180d_customers": k, "repeat_rate_180d": rate, "ci95_low": low, "ci95_high": high}

    late = first_orders[first_orders.delivery_group == "Late"]
    ontime = first_orders[first_orders.delivery_group == "On time or early"]
    if len(late) and len(ontime):
        counts = [int(late.repeat_180d.sum()), int(ontime.repeat_180d.sum())]
        nobs = [int(len(late)), int(len(ontime))]
        z, p = proportions_ztest(counts, nobs)
        ci_low, ci_high = confint_proportions_2indep(counts[0], nobs[0], counts[1], nobs[1], method="newcomb")
        stats["repeat_difference_late_minus_ontime"] = {
            "difference": stats["Late"]["repeat_rate_180d"] - stats["On time or early"]["repeat_rate_180d"],
            "ci95_low": float(ci_low), "ci95_high": float(ci_high), "z_stat": float(z), "p_value": float(p),
        }
    else:
        stats["repeat_difference_late_minus_ontime"] = {"difference": None, "ci95_low": None, "ci95_high": None, "z_stat": None, "p_value": None}

    # Review association: delivered orders grouped by days-vs-estimate; difference is late minus on-time.
    late_reviews = d.loc[d.days_vs_estimate > 0, "review_score"].dropna().to_numpy(dtype=float)
    ontime_reviews = d.loc[d.days_vs_estimate <= 0, "review_score"].dropna().to_numpy(dtype=float)
    if len(late_reviews) and len(ontime_reviews):
        mw = mannwhitneyu(late_reviews, ontime_reviews, alternative="two-sided")
        low, high = _bootstrap_mean_diff(late_reviews, ontime_reviews)
        review_stats = {
            "late_n_with_review": int(len(late_reviews)),
            "ontime_n_with_review": int(len(ontime_reviews)),
            "late_mean_review": float(late_reviews.mean()),
            "ontime_mean_review": float(ontime_reviews.mean()),
            "mean_difference_late_minus_ontime": float(late_reviews.mean() - ontime_reviews.mean()),
            "bootstrap_ci95_low": low,
            "bootstrap_ci95_high": high,
            "mann_whitney_u": float(mw.statistic),
            "mann_whitney_p_value": float(mw.pvalue),
        }
    else:
        review_stats = {"late_n_with_review": int(len(late_reviews)), "ontime_n_with_review": int(len(ontime_reviews))}
    stats["review_difference"] = review_stats
    return delay_summary, pd.DataFrame(repeat_rows), stats


def _make_charts(cohort: pd.DataFrame, segments: pd.DataFrame, delays: pd.DataFrame, repeat_by_delivery: pd.DataFrame) -> list[str]:
    FIGURES.mkdir(parents=True, exist_ok=True)
    produced: list[str] = []
    plt.rcParams.update({"figure.dpi": 120, "savefig.dpi": 180})

    c = cohort.copy()
    c["cohort_month"] = pd.to_datetime(c["cohort_month"])
    heat = c[(c.cohort_month >= pd.Timestamp("2017-01-01")) & (c.cohort_month <= pd.Timestamp("2018-08-01")) & (c.month_index.between(1, 12))]
    if not heat.empty:
        pivot = heat.pivot(index="cohort_month", columns="month_index", values="retention_rate")
        pivot = pivot.reindex(columns=list(range(1, 13)))
        fig, ax = plt.subplots(figsize=(12, 7))
        im = ax.imshow(pivot.to_numpy(), aspect="auto", interpolation="nearest")
        ax.set_yticks(range(len(pivot.index)), [pd.Timestamp(v).strftime("%Y-%m") for v in pivot.index])
        ax.set_xticks(range(12), [f"M{i}" for i in range(1, 13)])
        ax.set_title("Customer cohort retention (cohorts Jan 2017–Aug 2018)")
        ax.set_xlabel("Months since first purchase")
        ax.set_ylabel("First-purchase cohort")
        fig.colorbar(im, ax=ax, label="Share of cohort active")
        fig.tight_layout()
        path = FIGURES / "cohort_heatmap.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        produced.append(str(path.relative_to(ROOT)))

    if not segments.empty:
        plot = segments.sort_values("revenue", ascending=True)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(plot["segment"], plot["revenue"])
        ax.set_title("Historical revenue by RFM segment")
        ax.set_xlabel("Payment value (BRL)")
        fig.tight_layout()
        path = FIGURES / "segment_revenue.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        produced.append(str(path.relative_to(ROOT)))

    if not delays.empty:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(delays["delay_bucket"], delays["avg_review_score"])
        ax.set_title("Average review score by delivery performance")
        ax.set_ylabel("Average review score (1–5)")
        ax.set_xlabel("Delivery bucket")
        ax.tick_params(axis="x", rotation=20)
        fig.tight_layout()
        path = FIGURES / "review_by_delivery_delay.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        produced.append(str(path.relative_to(ROOT)))

    if not repeat_by_delivery.empty:
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.bar(repeat_by_delivery["delivery_group"], repeat_by_delivery["repeat_rate_180d"])
        ax.set_title("Second purchase within 180 days by first-order delivery")
        ax.set_ylabel("Repeat rate")
        ax.tick_params(axis="x", rotation=10)
        fig.tight_layout()
        path = FIGURES / "repeat_rate_by_delivery.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        produced.append(str(path.relative_to(ROOT)))
    return produced


def _fmt_pct(value: Any) -> str:
    return "not available" if value is None or pd.isna(value) else f"{float(value):.2%}"


def _fmt_money(value: Any) -> str:
    return "not available" if value is None or pd.isna(value) else f"R$ {float(value):,.2f}"


def _write_docs(profile: dict[str, Any], headline: dict[str, Any], rfm_meta: dict[str, Any], segments: pd.DataFrame,
                second_by_cohort: pd.DataFrame, delay_summary: pd.DataFrame, delivery_stats: dict[str, Any], charts: list[str]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    validation = profile["validation"]
    recon = profile["revenue_reconciliation"]
    notes_lines = [
        "# Data notes and validation results", "",
        "Generated by `scripts/run_analysis.py` from the local Olist dataset. Do not hand-edit figures here; rerun the pipeline after a data change.", "",
        "## Source profile", "",
        f"- Source purchase timestamp range: `{profile['source_date_min']}` to `{profile['source_date_max']}`.",
        "- The source contains multiple relational CSVs. The core pipeline loads customers, orders, payments and reviews; order items and other optional files are profiled when present.",
        "- Row counts by loaded raw table:",
    ]
    notes_lines += [f"  - `{k}`: {v:,} rows" for k, v in sorted(profile["raw_table_row_counts"].items())]
    notes_lines += ["", "## Join-grain validation", "",
                    f"- `orders_enriched` rows: {validation['rows']:,}",
                    f"- Distinct `order_id`: {validation['distinct_orders']:,}",
                    f"- Duplicate order rows: {validation['duplicate_order_rows']:,}",
                    f"- Orders without a review: {validation['orders_without_review']:,}",
                    f"- Orders without delivery date: {validation['orders_without_delivery_date']:,}",
                    f"- Orders without payment value: {validation['orders_without_payment_value']:,}",
                    "", "## Revenue reconciliation", "",
                    f"- Sum of `order_value` in `orders_enriched`: {_fmt_money(recon['enriched_payment_value'])}",
                    f"- Sum of source payment rows for included orders: {_fmt_money(recon['source_payment_value'])}",
                    "- Payments are aggregated to one row per order before joining. Reviews are reduced to the latest answer timestamp per order. `order_items` is not joined into the order-level table, avoiding a row-multiplication fan-out.",
                    "", "## Duplicate and grain diagnostics", ""]
    notes_lines += [f"- Extra review rows beyond unique orders: {profile['duplicate_diagnostics']['extra_review_rows']:,}",
                    f"- Extra payment rows beyond unique orders: {profile['duplicate_diagnostics']['extra_payment_rows']:,}",
                    f"- Customer rows beyond unique `customer_unique_id`: {profile['duplicate_diagnostics']['extra_customer_identity_rows']:,}",
                    "", "## Decisions", "",
                    "- Cancelled and unavailable orders are excluded from `orders_enriched`; all remaining statuses are eligible for general repeat/RFM analysis.",
                    "- Delivery analysis is restricted to delivered orders with an actual delivered date.",
                    "- A delivery is late when the delivered **calendar date** is later than the estimated delivery calendar date; same-day afternoon delivery is not marked late.",
                    "- RFM uses `customer_unique_id` as person-level identity, one day after the latest eligible purchase as the snapshot date, five quantile buckets for Recency and Monetary value, and a binary Repeat/One-time frequency flag.",
                    "- For 90/180-day meaningful second-purchase metrics, the second eligible order must occur at least 24 hours after the first order to reduce same-day basket-split inflation.",
                    "- Cohort chart excludes early sparse cohorts and late/right-censored cohorts from its default heatmap view (January 2017–August 2018); the exported long cohort file retains all cohort months.",
                    "", "## Generated charts", ""]
    notes_lines += [f"- `{p}`" for p in charts]
    (DOCS / "data_notes.md").write_text("\n".join(notes_lines) + "\n", encoding="utf-8")

    top = segments.iloc[0] if not segments.empty else None
    repeat_by_180 = pd.DataFrame()
    if not second_by_cohort.empty:
        elig = second_by_cohort[second_by_cohort["eligible_customers_180d"] > 0]
        n180 = int(elig["eligible_customers_180d"].sum())
        k180 = int(elig["repeat_180d"].sum())
        n90 = int(second_by_cohort[second_by_cohort["eligible_customers_90d"] > 0]["eligible_customers_90d"].sum())
        k90 = int(second_by_cohort[second_by_cohort["eligible_customers_90d"] > 0]["repeat_90d"].sum())
        rate90 = k90 / n90 if n90 else np.nan
        rate180 = k180 / n180 if n180 else np.nan
    else:
        n90 = k90 = n180 = k180 = 0
        rate90 = rate180 = np.nan
    repeat_diff = delivery_stats.get("repeat_difference_late_minus_ontime", {})
    review_diff = delivery_stats.get("review_difference", {})
    memo = [
        "# Recommendation memo: Olist customer retention and RFM", "",
        "**Decision:** use the dataset-derived segment score as a screening recommendation, then validate it with a controlled retention test. The results are descriptive and cannot establish causality.", "",
        "## Headline", "",
        f"- Eligible customers: **{headline['customers']:,}** across **{headline['eligible_orders']:,} eligible orders**.",
        f"- Customers with 2+ eligible orders: **{headline['repeat_customers']:,} ({_fmt_pct((headline['repeat_pct'] or 0) / 100 if headline['repeat_pct'] is not None else None)})**.",
        f"- Eligible payment value: **{_fmt_money(headline['total_revenue'])}**; share from repeat customers: **{_fmt_pct((headline['repeat_revenue_pct'] or 0) / 100 if headline['repeat_revenue_pct'] is not None else None)}**.",
        f"- Second order at least 24 hours after the first within 90 days: **{k90:,}/{n90:,} ({_fmt_pct(rate90)})** among customers with sufficient follow-up.",
        f"- Same meaningful second-order rule within 180 days: **{k180:,}/{n180:,} ({_fmt_pct(rate180)})** among customers with sufficient follow-up.",
    ]
    if top is not None:
        memo += ["", "## Candidate segment to test first", "",
                 f"**{top['segment']}** ranked highest under the explicit screening score (30% customer-size percentile, 30% average-spend percentile, 20% recency/reachability percentile, 20% lower-review/service-signal percentile). This is a decision aid, not a validated propensity model.",
                 f"- Customers: {int(top['customers']):,} ({_fmt_pct(top['pct_customers'])} of customers)",
                 f"- Historical revenue: {_fmt_money(top['revenue'])} ({_fmt_pct(top['pct_revenue'])} of eligible revenue)",
                 f"- Average historical spend per customer: {_fmt_money(top['avg_spend_per_customer'])}",
                 f"- Average days since last purchase: {top['avg_days_since_last_order']:.1f}",
                 f"- Average associated review score: {top['avg_review']:.2f}" if pd.notna(top['avg_review']) else "- Average associated review score: unavailable",
                 f"- Assumed extra revenue at +1/+2/+3 percentage-point reactivation uplift: {_fmt_money(top['revenue_at_1pp_uplift'])} / {_fmt_money(top['revenue_at_2pp_uplift'])} / {_fmt_money(top['revenue_at_3pp_uplift'])}.",
                 "- These uplift amounts are scenario values calculated using historical average spend per customer; they are not a forecast, margin estimate, or incremental value proven by an experiment."]
    memo += ["", "## Delivery and review evidence", ""]
    if "Late" in delivery_stats and "On time or early" in delivery_stats:
        late_s = delivery_stats["Late"]
        on_s = delivery_stats["On time or early"]
        memo += [f"- First-order 180-day repeat rate, late delivery: {_fmt_pct(late_s['repeat_rate_180d'])} ({late_s['repeat_180d_customers']:,}/{late_s['n']:,}; 95% Wilson CI {_fmt_pct(late_s['ci95_low'])}–{_fmt_pct(late_s['ci95_high'])}).",
                 f"- First-order 180-day repeat rate, on-time/early delivery: {_fmt_pct(on_s['repeat_rate_180d'])} ({on_s['repeat_180d_customers']:,}/{on_s['n']:,}; 95% Wilson CI {_fmt_pct(on_s['ci95_low'])}–{_fmt_pct(on_s['ci95_high'])})."]
    if repeat_diff.get("p_value") is not None:
        memo.append(f"- Difference in repeat rate (late minus on-time/early): {_fmt_pct(repeat_diff['difference'])}; 95% CI {_fmt_pct(repeat_diff['ci95_low'])} to {_fmt_pct(repeat_diff['ci95_high'])}; two-proportion z-test p = {repeat_diff['p_value']:.4g}.")
    if review_diff.get("mean_difference_late_minus_ontime") is not None:
        memo.append(f"- Mean review-score difference (late minus on-time/early): {review_diff['mean_difference_late_minus_ontime']:.3f} points; bootstrap 95% CI {review_diff['bootstrap_ci95_low']:.3f} to {review_diff['bootstrap_ci95_high']:.3f}; Mann–Whitney p = {review_diff['mann_whitney_p_value']:.4g}.")
    if not delay_summary.empty:
        memo += ["", "### Average review by delivery bucket", "", "| Delivery bucket | Orders | Average review | 1–2 star share |", "|---|---:|---:|---:|"]
        for _, row in delay_summary.iterrows():
            avg = f"{row['avg_review_score']:.2f}" if pd.notna(row['avg_review_score']) else "—"
            bad = _fmt_pct(row['pct_1_2_star'])
            memo.append(f"| {row['delay_bucket']} | {int(row['orders']):,} | {avg} | {bad} |")
    memo += ["", "## Action", "",
             "1. Test a low-cost segment-specific re-engagement message or second-purchase offer; keep a random holdout and measure incremental 90/180-day repeat purchases and contribution margin before scaling.",
             "2. If delivered-late customers show materially worse reviews, test a proactive service-recovery message for late deliveries and track review/repeat outcomes separately.",
             "3. Review segment size, reachability, and service evidence jointly before choosing a campaign. Include contactability and campaign cost in the next iteration.",
             "", "## Limitations", "",
             "- Historical, anonymised Olist marketplace data from 2016–2018; one market and not current live-store performance.",
             "- Customers are identified using `customer_unique_id`; `customer_id` is order-specific and is not suitable as a person-level repeat key.",
             "- Payment and review tables are aggregated before joining. Validation checks enforce one row per eligible order and reconcile payment value.",
             "- Same-day or sub-24-hour second orders are excluded from meaningful 90/180-day second-order metrics, but still count toward RFM frequency and the broad 2+ order statistic.",
             "- Delivery/review and delivery/repeat comparisons are observational. State, seller, category, order value, and other factors can confound the relationships.",
             "- Revenue uplift cases are explicit assumptions and exclude margin, incentive costs, contactability, and cannibalisation.",
             "", "## Recommended decision", "",
             "Proceed to a controlled re-engagement test for the selected segment only after campaign costs, channel eligibility, and the holdout design are defined. Do not describe these observational results as proof that delivery delay causes churn.",
             ""]
    (DOCS / "recommendation_memo.md").write_text("\n".join(memo), encoding="utf-8")


def run() -> dict[str, Any]:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as con:
        raw_counts = _load_tables(con)
        profile = _profile_and_validate(con, raw_counts)
        orders = con.execute("SELECT * FROM orders_enriched").df()
        orders["purchase_ts"] = pd.to_datetime(orders["purchase_ts"], errors="coerce")
        orders["delivered_ts"] = pd.to_datetime(orders["delivered_ts"], errors="coerce")
        orders["estimated_ts"] = pd.to_datetime(orders["estimated_ts"], errors="coerce")
        orders["review_score"] = pd.to_numeric(orders["review_score"], errors="coerce")
        orders["days_vs_estimate"] = pd.to_numeric(orders["days_vs_estimate"], errors="coerce")
        orders["is_late"] = pd.to_numeric(orders["is_late"], errors="coerce")

        repeat_metrics, second_by_cohort, cohort, repeat_info = _build_repeat_and_cohorts(orders)
        rfm_customers, segments, rfm_meta = _build_rfm(orders)
        delay_summary, repeat_by_delivery, delivery_stats = _build_delivery_analysis(orders, repeat_info["firsts"])

        # Export local detail for Power BI; .gitignore keeps these row-level files out of Git.
        orders.to_csv(PROCESSED / "orders_enriched.csv", index=False)
        rfm_customers.to_csv(PROCESSED / "rfm_customers.csv", index=False)
        repeat_metrics.to_csv(PROCESSED / "repeat_metrics.csv", index=False)
        second_by_cohort.to_csv(PROCESSED / "second_order_by_cohort.csv", index=False)
        cohort.to_csv(PROCESSED / "cohort_retention.csv", index=False)
        segments.to_csv(PROCESSED / "segment_summary.csv", index=False)
        delay_summary.to_csv(PROCESSED / "delay_summary.csv", index=False)
        repeat_by_delivery.to_csv(PROCESSED / "repeat_by_delivery.csv", index=False)
        # Small, shareable aggregate tables; ensure no customer identifiers are included.
        segments.to_csv(PROCESSED / "segment_summary_public.csv", index=False)
        delay_summary.to_csv(PROCESSED / "delay_summary_public.csv", index=False)
        cohort.to_csv(PROCESSED / "cohort_retention_public.csv", index=False)

        charts = _make_charts(cohort, segments, delay_summary, repeat_by_delivery)
        _write_docs(profile, repeat_info["headline"], rfm_meta, segments, second_by_cohort, delay_summary, delivery_stats, charts)
        summary = {
            "profile": profile,
            "repeat_metrics": repeat_info["headline"],
            "rfm": rfm_meta,
            "segment_summary": segments.round(6).to_dict(orient="records"),
            "delivery_statistics": delivery_stats,
            "outputs": [str(p.relative_to(ROOT)) for p in sorted(PROCESSED.glob("*.csv"))] + charts,
            "note": "All reported values are computed from the input data during this run. Uplift cases are assumptions, not forecasts."
        }
        # Convert numpy/pandas scalar leftovers to JSON-safe types via pandas JSON round-trip.
        safe_summary = json.loads(pd.Series([summary]).to_json(orient="values", date_format="iso"))[0]
        (PROCESSED / "analysis_summary.json").write_text(json.dumps(safe_summary, indent=2, ensure_ascii=False), encoding="utf-8")
        (PROCESSED / "validation.json").write_text(json.dumps(profile["validation"], indent=2), encoding="utf-8")
    return summary


def main() -> None:
    try:
        summary = run()
    except Exception as exc:
        print(f"ANALYSIS FAILED: {exc}", file=sys.stderr)
        raise
    print("Olist analysis completed successfully. Review the actual outputs below:")
    print(json.dumps({
        "eligible_customers": summary["repeat_metrics"]["customers"],
        "eligible_orders": summary["repeat_metrics"]["eligible_orders"],
        "repeat_customer_pct": summary["repeat_metrics"]["repeat_pct"],
        "recommended_segment_candidate": summary["rfm"]["recommended_segment"],
        "outputs_directory": str(PROCESSED),
        "memo": str(DOCS / "recommendation_memo.md"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
