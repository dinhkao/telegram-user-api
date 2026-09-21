from datetime import date

from sales_dashboard.compute import _daily, _summary, sales_dashboard_data, today_sales_summary


def row(entry, day, customer, items, revenue, kind="sale"):
    return {
        "entry_id": entry,
        "kind": kind,
        "ymd": day,
        "customer": customer,
        "revenue": revenue,
        "items": items,
    }


def item(code, qty, revenue):
    return {"code": code, "qty": qty, "revenue": revenue}


def test_summary_reports_gross_returns_and_net_values():
    rows = [
        row("order:1", "2026-09-11", "Khách A", [item("A", 10, 1_000)], 1_000),
        row("order:2", "2026-09-11", "Khách B", [item("A", 1, 200), item("B", 2, 300)], 500),
        row("return:1", "2026-09-11", "Khách A", [item("A", -3, -300)], -300, "return"),
    ]

    result = _summary(rows)

    assert result == {
        "net_qty": 10,
        "gross_qty": 13,
        "return_qty": 3,
        "revenue": 1_200,
        "gross_revenue": 1_500,
        "return_revenue": 300,
        "orders": 2,
        "returns": 1,
        "customers": 2,
        "products": 2,
        "avg_order_value": 750,
    }


def test_daily_fills_dates_without_transactions():
    rows = [row("order:1", "2026-09-10", "Khách A", [item("A", 2, 400)], 400)]

    result = _daily(rows, date(2026, 9, 9), date(2026, 9, 11))

    assert [day["day"] for day in result] == ["2026-09-09", "2026-09-10", "2026-09-11"]
    assert [day["net_qty"] for day in result] == [0, 2, 0]


def test_today_summary_exposes_sales_metrics_without_profit_fields(monkeypatch):
    rows = [
        row("order:1", "2026-09-11", "Khách A", [item("A", 2, 500)], 500),
        row("return:1", "2026-09-11", "Khách A", [item("A", -1, -200)], -200, "return"),
    ]
    monkeypatch.setattr("sales_dashboard.compute.scan_orders", lambda conn, since, until, quality: rows)

    result = today_sales_summary(object(), "2026-09-11")

    assert result["summary"]["revenue"] == 300
    assert result["today"] == "2026-09-11"
    assert "profit" not in result["summary"]
    assert "cost" not in result["summary"]


def test_dashboard_compares_week_and_month_to_same_elapsed_days(monkeypatch):
    rows = [
        row("order:today", "2026-09-11", "Khách mới", [item("A", 5, 500)], 500),
        row("order:prev-week", "2026-09-04", "Khách cũ", [item("A", 2, 200)], 200),
        row("order:prev-month", "2026-08-11", "Khách cũ", [item("B", 1, 100)], 100),
    ]
    monkeypatch.setattr("sales_dashboard.compute.scan_orders", lambda conn, since, until, quality: rows)
    monkeypatch.setattr("sales_dashboard.compute.get_all_products", lambda conn: [{"code": "A", "name": "Kẹo A"}, {"code": "B", "name": "Kẹo B"}])

    result = sales_dashboard_data(object(), "2026-09-01", "2026-09-11", "2026-09-11")

    assert result["headline"]["week"]["previous_since"] == "2026-08-31"
    assert result["headline"]["week"]["previous_until"] == "2026-09-04"
    assert result["headline"]["month"]["previous_since"] == "2026-08-01"
    assert result["headline"]["month"]["previous_until"] == "2026-08-11"
    assert result["headline"]["week"]["changes"]["revenue"] == 150.0
    assert result["selected"]["top_products"][0]["name"] == "Kẹo A"


def test_single_day_filter_uses_its_full_week_for_chart(monkeypatch):
    rows = [row("order:today", "2026-09-11", "Khách A", [item("A", 1, 100)], 100)]
    monkeypatch.setattr("sales_dashboard.compute.scan_orders", lambda conn, since, until, quality: rows)
    monkeypatch.setattr("sales_dashboard.compute.get_all_products", lambda conn: [{"code": "A", "name": "Kẹo A"}])

    result = sales_dashboard_data(object(), "2026-09-11", "2026-09-11", "2026-09-11")
    selected = result["selected"]

    assert selected["since"] == selected["until"] == "2026-09-11"
    assert selected["chart_since"] == "2026-09-07"
    assert selected["chart_until"] == "2026-09-13"
    assert selected["chart_selected_day"] == "2026-09-11"
    assert [point["day"] for point in selected["daily"]] == [
        "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10",
        "2026-09-11", "2026-09-12", "2026-09-13",
    ]
