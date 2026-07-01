"""Typed façade over the order JSON blob — Phase 2 strangler step.

An order currently lives as one untyped `json` dict. `Order` wraps that dict and
gives typed, named access to the well-known fields WITHOUT converting to a fixed
schema. It is deliberately **lossless**: it holds the original dict and only
mutates keys it is explicitly told to, so adopting it never drops or adds blob
fields (important — the blob is also read by Firebase and the Node app).

This is the seam future work grows behind: as fields are promoted to real columns
(Phase 3), callers keep using `Order` and only this file changes. See
`docs/senior-review.md`. Pure — no IO. Connects to: order_store.domain (logic),
order_store.tasks (adoption site).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Order:
    """Typed handle on one order's JSON dict. `data` is the live blob."""

    data: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Order":
        return cls(d)

    def to_dict(self) -> dict:
        return self.data

    # --- typed access to well-known fields (read via .get, never inserts) ---
    @property
    def task_status(self) -> dict:
        return self.data.get("task_status") or {}

    def set_field(self, key: str, value) -> None:
        self.data[key] = value

    def del_field(self, key: str) -> None:
        self.data.pop(key, None)
