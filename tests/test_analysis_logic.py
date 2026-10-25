"""Small synthetic unit tests. These validate code paths only; they are not Olist results."""
import pandas as pd

from src.olist_analysis import _build_repeat_and_cohorts, _build_rfm, _build_delivery_analysis


def toy_orders():
    rows = []
    base = pd.Timestamp("2017-01-01")
    for i in range(20):
        count = 2 if i % 4 == 0 else 1
        for j in range(count):
            purchase = base + pd.Timedelta(days=i * 20 + j * 60)
            delivered = purchase + pd.Timedelta(days=8 if i % 2 else 6)
            estimated = purchase + pd.Timedelta(days=7)
            rows.append({
                "order_id": f"order-{i}-{j}",
                "customer_unique_id": f"customer-{i}",
                "customer_state": "SP",
                "order_status": "delivered",
                "purchase_ts": purchase,
                "delivered_ts": delivered,
                "estimated_ts": estimated,
                "order_value": float(80 + i * 11),
                "review_score": 2 if i % 2 else 5,
                "days_vs_estimate": (delivered.date() - estimated.date()).days,
                "is_late": int((delivered.date() - estimated.date()).days > 0),
            })
    return pd.DataFrame(rows)


def test_repeat_and_cohort_outputs_have_expected_grain():
    orders = toy_orders()
    metrics, second_by_cohort, cohort, info = _build_repeat_and_cohorts(orders)
    assert metrics.loc[0, "customers"] == 20
    assert metrics.loc[0, "eligible_orders"] == orders.order_id.nunique()
    assert set(["cohort_month", "month_index", "active_customers", "cohort_customers", "retention_rate"]).issubset(cohort.columns)
    assert cohort.retention_rate.between(0, 1).all()
    assert not second_by_cohort.empty
    assert len(info["firsts"]) == 20


def test_rfm_returns_scores_and_segments():
    rfm, summary, meta = _build_rfm(toy_orders())
    assert rfm.customer_unique_id.nunique() == 20
    assert rfm.R.between(1, 5).all()
    assert rfm.M.between(1, 5).all()
    assert set(rfm.F.unique()).issubset({"Repeat", "One-time"})
    assert "segment" in rfm.columns and not summary.empty
    assert meta["recommended_segment"] in set(summary.segment)


def test_delivery_analysis_returns_comparison_groups():
    orders = toy_orders()
    _, _, _, info = _build_repeat_and_cohorts(orders)
    delay, repeat_by_delivery, stats = _build_delivery_analysis(orders, info["firsts"])
    assert not delay.empty
    assert set(repeat_by_delivery.delivery_group).issubset({"Late", "On time or early"})
    assert "repeat_difference_late_minus_ontime" in stats
    assert "review_difference" in stats
