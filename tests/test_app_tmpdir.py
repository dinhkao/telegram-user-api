"""Thư mục tạm của tiến trình phải nằm trên SSD (cạnh app.db/ảnh), không rơi vào
/var/folders của ổ trong — nơi từng gây [Errno 28] lúc upload ảnh / render PNG.

Kiểm: utils.paths.use_app_tmpdir (đặt tempfile.tempdir + TMPDIR + dọn rác cũ).
"""
from __future__ import annotations

import os
import tempfile
import time

import pytest

import utils.paths as paths


@pytest.fixture
def restore_tmp():
    """Trả lại tempfile.tempdir / TMPDIR / APP_TMP_DIR sau mỗi test."""
    old_dir, old_env, old_app = tempfile.tempdir, os.environ.get("TMPDIR"), paths.APP_TMP_DIR
    yield
    tempfile.tempdir, paths.APP_TMP_DIR = old_dir, old_app
    if old_env is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = old_env


def test_tro_tempdir_sang_app_tmp_dir(tmp_path, restore_tmp):
    paths.APP_TMP_DIR = str(tmp_path / "tmp")
    assert paths.use_app_tmpdir() == paths.APP_TMP_DIR
    assert tempfile.gettempdir() == paths.APP_TMP_DIR
    assert os.environ["TMPDIR"] == paths.APP_TMP_DIR
    with tempfile.NamedTemporaryFile() as f:
        assert f.name.startswith(paths.APP_TMP_DIR)


def test_don_file_tam_cu_giu_file_moi(tmp_path, restore_tmp):
    d = tmp_path / "tmp"
    d.mkdir()
    old, new = d / "cu.png", d / "moi.png"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    os.utime(old, (time.time() - 48 * 3600,) * 2)

    paths.APP_TMP_DIR = str(d)
    paths.use_app_tmpdir(max_age_hours=24)

    assert not old.exists()
    assert new.exists()


def test_ssd_khong_ghi_duoc_thi_giu_mac_dinh(tmp_path, restore_tmp):
    """SSD chưa mount → không được đổi tempdir (ghi vào chỗ không tồn tại còn tệ hơn)."""
    chan = tmp_path / "file-chu-khong-phai-thu-muc"
    chan.write_bytes(b"x")
    paths.APP_TMP_DIR = str(chan / "tmp")
    truoc = tempfile.tempdir

    assert paths.use_app_tmpdir() is None
    assert tempfile.tempdir == truoc
