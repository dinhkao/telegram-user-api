"""Build id webapp (server_app/app_build.py) — nguồn của {"type":"hello"} trên /ws.

Sai ở đây có 2 kiểu hỏng đều tệ: trả rỗng/sai → máy chạy bundle cũ mãi không biết;
hoặc đổi giá trị dù bundle không đổi → mọi máy tải lại vô cớ giữa lúc đang làm.
"""
from __future__ import annotations

import os

from server_app import app_build

_HTML = (
    '<!doctype html><html><head><title>x</title>'
    '<script type="module" crossorigin src="./assets/{js}"></script>'
    '<link rel="stylesheet" href="./assets/index-AbC123.css"></head>'
    '<body><div id="app"></div></body></html>'
)


def _use(tmp_path, monkeypatch, js: str) -> str:
    index = tmp_path / "index.html"
    index.write_text(_HTML.format(js=js), encoding="utf-8")
    monkeypatch.setattr(app_build, "_INDEX", str(index))
    monkeypatch.setattr(app_build, "_cached", None)
    return str(index)


def test_lay_ten_bundle_js(tmp_path, monkeypatch):
    _use(tmp_path, monkeypatch, "index-sqyUf3YA.js")
    assert app_build.build_id() == "index-sqyUf3YA.js"


def test_khong_lay_nham_file_css(tmp_path, monkeypatch):
    _use(tmp_path, monkeypatch, "index-JS12_ab-.js")
    assert app_build.build_id().endswith(".js")


def test_doi_khi_build_lai(tmp_path, monkeypatch):
    index = _use(tmp_path, monkeypatch, "index-aaaaaaaa.js")
    assert app_build.build_id() == "index-aaaaaaaa.js"
    # ghi đè bằng bundle khác + đẩy mtime để chắc chắn khác lần trước
    with open(index, "w", encoding="utf-8") as f:
        f.write(_HTML.format(js="index-bbbbbbbb.js"))
    os.utime(index, (0, 0))
    assert app_build.build_id() == "index-bbbbbbbb.js"


def test_chua_build_thi_rong(tmp_path, monkeypatch):
    monkeypatch.setattr(app_build, "_INDEX", str(tmp_path / "khong-co.html"))
    monkeypatch.setattr(app_build, "_cached", None)
    # rỗng = client BỎ QUA kiểm tra (không ép reload nhầm)
    assert app_build.build_id() == ""


def test_index_khong_co_bundle_thi_rong(tmp_path, monkeypatch):
    index = tmp_path / "index.html"
    index.write_text("<html><body>chưa build</body></html>", encoding="utf-8")
    monkeypatch.setattr(app_build, "_INDEX", str(index))
    monkeypatch.setattr(app_build, "_cached", None)
    assert app_build.build_id() == ""
