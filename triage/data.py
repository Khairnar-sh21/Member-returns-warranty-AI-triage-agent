"""Load the synthetic member, order, and case-history data."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, ConfigDict, field_validator

from triage.config import DATA_DIR, MembershipStatus, Region

CHARGER_SKU = "PB4-CHGR"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class Member(_Record):
    member_id: str
    name: str
    email: str
    country: str
    region: Region
    membership_status: MembershipStatus
    membership_start_date: date
    plan: str


class Order(_Record):
    order_id: str
    member_id: str
    order_date: date
    delivered_date: date | None
    sku: str
    ship_from_warehouse: str
    order_status: str

    @field_validator("delivered_date", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        return value or None

    @property
    def is_device(self) -> bool:
        return self.sku.startswith("PB4-") and self.sku != CHARGER_SKU


class PriorCase(_Record):
    prior_case_id: str
    member_id: str
    case_date: date
    category: str
    outcome: str


class MemberContext(_Record):
    """Everything the rules engine knows about one member."""

    member: Member
    orders: list[Order]
    prior_cases: list[PriorCase]

    def latest_order(self) -> Order | None:
        return max(self.orders, key=lambda o: o.order_date, default=None)

    def latest_delivered_order(self, devices_only: bool = False) -> Order | None:
        candidates = [
            o for o in self.orders if o.delivered_date and (o.is_device or not devices_only)
        ]
        return max(candidates, key=lambda o: o.delivered_date, default=None)


class DataStore:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        read = lambda name: pd.read_csv(data_dir / name, dtype=str, keep_default_na=False)  # noqa: E731
        self.members = {
            row["member_id"]: Member(**row) for row in read("members.csv").to_dict("records")
        }
        self._orders = [Order(**row) for row in read("orders.csv").to_dict("records")]
        self._cases = [PriorCase(**row) for row in read("prior_cases.csv").to_dict("records")]

    def get_context(self, member_id: str | None) -> MemberContext | None:
        member = self.members.get(member_id or "")
        if member is None:
            return None
        return MemberContext(
            member=member,
            orders=[o for o in self._orders if o.member_id == member_id],
            prior_cases=[c for c in self._cases if c.member_id == member_id],
        )


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    return DataStore()
