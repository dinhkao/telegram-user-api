"""forecast_store — DỰ BÁO HÀNG HOÁ HẰNG NGÀY (bảng `daily_forecasts` + `forecast_views`
trong app.db, 100% local).

Mỗi sáng 7h job `tools/forecast_daily.sh` chạy engine (`engine.compute`, thuần, đọc lịch
sử đơn qua `history.load_lines`, gắn âm lịch `lunar.solar2lunar`) → agent Claude viết
nhận định → `tools/forecast_publish.py` đăng qua POST /api/forecasts/publish (loopback).
Không có agent thì `narrative.auto_narrative` tự viết. Dùng bởi server_app/forecast_routes.
"""
from .queries import (get_by_ymd, get_forecast, list_forecasts, mark_viewed, upsert_forecast,
                      viewed_by)
from .schema import ensure_tables

__all__ = ["ensure_tables", "upsert_forecast", "list_forecasts", "get_forecast", "get_by_ymd",
           "mark_viewed", "viewed_by"]
