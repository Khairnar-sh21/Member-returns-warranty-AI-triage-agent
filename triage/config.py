"""Load and validate rules.yaml.

Validation matters because rules.yaml is meant to be edited by non-engineers:
a typo or a missing threshold should fail loudly at startup, not silently
change a member's eligibility.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = PROJECT_ROOT / "rules.yaml"
DATA_DIR = PROJECT_ROOT / "data"

Region = Literal["US", "CA", "UK", "EU", "AU"]
Warehouse = Literal["US", "EU", "APAC"]
Priority = Literal["low", "normal", "high", "urgent"]
Category = Literal[
    "troubleshooting",
    "warranty_replacement",
    "return_remorse",
    "shipping_delivery",
    "billing_membership",
    "safety_concern",
    "other",
]

PRIORITY_ORDER: list[Priority] = ["low", "normal", "high", "urgent"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyMeta(_Strict):
    version: str
    as_of_date: date | None = None


class ReturnRemorseRules(_Strict):
    window_days: int = Field(gt=0)
    queue: str


class ReplacementLimit(_Strict):
    max_replacements: int = Field(ge=0)
    rolling_window_months: int = Field(gt=0)
    over_limit_action: str


class WarrantyRules(_Strict):
    default_months: int = Field(gt=0)
    months_by_region: dict[Region, int] = {}
    required_membership_status: Literal["active", "past_due", "cancelled"]
    past_due_action: str
    cancelled_action: str
    replacement_limit: ReplacementLimit
    queue: str


class TroubleshootingRules(_Strict):
    sub_categories: list[str]
    skip_if_member_already_troubleshot: bool
    queue: str


class ShippingRules(_Strict):
    lost_package_business_days: int = Field(gt=0)
    queue: str


class BillingRules(_Strict):
    queue: str
    allow_rma: bool


class AngryHighValue(_Strict):
    sentiments: list[str]
    plans: list[Literal["monthly", "annual"]]


class PossibleFraud(_Strict):
    min_prior_cases: int = Field(gt=0)
    window_days: int = Field(gt=0)


class SafetyRules(_Strict):
    priority: Priority
    queue: str
    keywords: list[str]


class EscalationRules(_Strict):
    min_confidence: float = Field(ge=0, le=1)
    angry_high_value: AngryHighValue
    possible_fraud: PossibleFraud
    safety: SafetyRules
    queue: str


class RoutingRules(_Strict):
    region_to_warehouse: dict[Region, Warehouse]


class PriorityRules(_Strict):
    default_by_category: dict[Category, Priority]


class Rules(_Strict):
    policy: PolicyMeta
    return_remorse: ReturnRemorseRules
    warranty: WarrantyRules
    troubleshooting_first: TroubleshootingRules
    shipping: ShippingRules
    billing: BillingRules
    escalation: EscalationRules
    routing: RoutingRules
    priority: PriorityRules

    def today(self) -> date:
        return self.policy.as_of_date or date.today()

    def warranty_months_for(self, region: str) -> int:
        return self.warranty.months_by_region.get(region, self.warranty.default_months)


class RulesConfigError(RuntimeError):
    """Raised with a human-readable message when rules.yaml is invalid."""


def load_rules(path: Path | str = RULES_PATH) -> Rules:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except FileNotFoundError as exc:
        raise RulesConfigError(f"Rules file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise RulesConfigError(f"rules.yaml is not valid YAML: {exc}") from exc

    try:
        return Rules.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise RulesConfigError(f"rules.yaml has invalid settings — {problems}") from exc


@lru_cache(maxsize=1)
def get_rules() -> Rules:
    return load_rules()
