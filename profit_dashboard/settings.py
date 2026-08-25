"""Dashboard settings: settings file I/O (tiền vay + trọng số tháng)."""
from __future__ import annotations
import json
import logging
import os

log = logging.getLogger("profit_dashboard")

# File JSON giữ cài đặt (tiền vay năm + trọng số tháng) — nằm ngoài repo như app.db.
SETTINGS_FILE = os.path.expanduser(
    os.getenv("PROFIT_SETTINGS_FILE", "~/letrang-db/profit_settings.json"))

DEFAULT_WEIGHTS = {str(m): 1.0 for m in range(1, 13)}


def load_settings():
    """Load dashboard settings from JSON file, ensuring weights exist."""
    default = {"yearly_loan_payment": 0, "monthly_weights": dict(DEFAULT_WEIGHTS)}
    if not os.path.exists(SETTINGS_FILE):
        return default
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Backward compat: convert monthly to yearly
        if "yearly_loan_payment" not in data:
            if "monthly_loan_payment" in data:
                data["yearly_loan_payment"] = data["monthly_loan_payment"] * 12
                del data["monthly_loan_payment"]
            else:
                data["yearly_loan_payment"] = 0
        # Backfill weights if missing
        if "monthly_weights" not in data:
            data["monthly_weights"] = dict(DEFAULT_WEIGHTS)
        else:
            # Ensure all 12 months present
            for m in range(1, 13):
                data["monthly_weights"].setdefault(str(m), 1.0)
        return data
    except:
        return default


def save_settings(settings):
    """Save dashboard settings to JSON file."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log.error(f"Failed to save settings: {e}")
        return False
