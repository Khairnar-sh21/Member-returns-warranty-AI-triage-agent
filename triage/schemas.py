"""Data contracts shared between the LLM classifier and the rules engine."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from triage.config import Category, Priority, Warehouse

Sentiment = Literal["positive", "neutral", "frustrated", "angry"]

# automated:    rules resolved it, no person needed
# needs_review: routine human check (low confidence, replacement limit, ...)
# escalated:    sensitive — safety, possible fraud, angry high-value member
Outcome = Literal["automated", "needs_review", "escalated"]

DecisionCode = Literal[
    "send_troubleshooting",
    "approve_warranty_replacement",
    "deny_out_of_warranty",
    "deny_membership_inactive",
    "hold_resolve_billing_first",
    "manual_review_replacement_limit",
    "approve_return",
    "deny_return_window_closed",
    "approve_lost_package_replacement",
    "wait_for_delivery",
    "investigate_delivery",
    "route_to_billing",
    "general_inquiry",
    "request_account_details",
    "no_eligible_order",
    "escalate_safety",
    "escalate_to_human",
]


class LLMClassification(BaseModel):
    """What the AI understood from the member's message. It contains no decision."""

    category: Category
    sub_category: str
    sentiment: Sentiment
    urgency: Priority
    extracted_facts: dict[str, str | int | float | bool | None] = {}
    member_already_troubleshot: bool = False
    confidence: float = Field(ge=0, le=1)
    reasoning_summary: str = ""

    @field_validator("sub_category")
    @classmethod
    def _normalize_sub_category(cls, value: str) -> str:
        return "_".join(value.strip().lower().replace("-", " ").split()) or "general"


class RuleResult(BaseModel):
    """One line of the decision trace."""

    rule_id: str
    group: Literal["safety", "account", "policy", "escalation", "priority"]
    name: str
    status: Literal["pass", "fail", "info", "skip"]
    reason_code: str
    detail: str


class FulfillmentPlan(BaseModel):
    """What the rules approved for shipping/returns; becomes the RMA in Phase 4."""

    rma_type: Literal["warranty_replacement", "remorse_return", "lost_package_replacement"]
    original_order_id: str
    sku: str
    replacement_sku: str | None
    warehouse: Warehouse
    return_label_required: bool
    ship_to_country: str


class Decision(BaseModel):
    decision: DecisionCode
    policy_outcome: DecisionCode
    automated: bool
    escalation_reasons: list[str]
    assigned_queue: str
    priority: Priority
    next_action: str
    reason_codes: list[str]
    trace: list[RuleResult]
    facts: dict[str, str] = {}  # policy facts the reply may quote (dates, windows)
    fulfillment: FulfillmentPlan | None
    policy_version: str
    as_of_date: date


# -----------------------------------------------------------------------------
# Business outputs (what downstream systems would receive)
# -----------------------------------------------------------------------------


class SupportCase(BaseModel):
    """CRM case (Salesforce-style). rma_id links it to the ERP record."""

    case_id: str
    member_id: str | None
    channel: str
    category: Category
    sub_category: str
    priority: Priority
    sentiment: Sentiment
    decision: DecisionCode
    reason_codes: list[str]
    next_action: str
    assigned_queue: str
    automated: bool
    outcome: Outcome
    ai_confidence: float
    rma_id: str | None
    policy_version: str
    created_at: datetime


class RMAOrder(BaseModel):
    """Return/replacement order (NetSuite-style). case_id links it back to the CRM."""

    rma_id: str
    case_id: str
    rma_type: Literal["warranty_replacement", "remorse_return", "lost_package_replacement"]
    original_order_id: str
    sku: str
    replacement_sku: str | None
    warehouse: Warehouse
    return_label_required: bool
    ship_to_country: str


class MemberReply(BaseModel):
    subject: str
    body: str
    guardrail_triggered: bool = False
