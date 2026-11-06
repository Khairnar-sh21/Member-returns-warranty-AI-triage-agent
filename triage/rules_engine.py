"""Deterministic rules engine: decides eligibility and next action.

Input:  the AI's classification of the message + the member's account data.
Output: a Decision with a plain-English trace of every rule evaluated.

The engine contains no AI. Given the same inputs and rules.yaml, it always
returns the same decision. Evaluation order:

  1. Safety        — injury/irritation signals go straight to a human (urgent)
  2. Policy        — category-specific eligibility (warranty, returns, ...)
  3. Escalation    — low confidence, angry high-value member, possible fraud
  4. Priority      — category default, raised by urgency or escalation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
from dateutil.relativedelta import relativedelta

from triage.config import PRIORITY_ORDER, Priority, Rules, get_rules
from triage.data import MemberContext, Order
from triage.schemas import (
    Decision,
    DecisionCode,
    FulfillmentPlan,
    LLMClassification,
    RuleResult,
)

HUMAN_REVIEW_OUTCOMES: set[DecisionCode] = {
    "manual_review_replacement_limit",
    "investigate_delivery",
    "general_inquiry",
    "no_eligible_order",
}


@dataclass
class _Outcome:
    code: DecisionCode
    queue: str
    next_action: str
    fulfillment: FulfillmentPlan | None = None
    facts: dict[str, str] = field(default_factory=dict)


class _Trace:
    def __init__(self) -> None:
        self.results: list[RuleResult] = []

    def add(self, rule_id, group, name, status, reason_code, detail) -> bool:
        self.results.append(
            RuleResult(
                rule_id=rule_id, group=group, name=name,
                status=status, reason_code=reason_code, detail=detail,
            )
        )
        return status != "fail"


def find_safety_keywords(message: str, keywords: list[str]) -> list[str]:
    """Whole-word, case-insensitive matches ("burn" matches "Burn", not "burnished")."""
    hits = []
    for keyword in keywords:
        pattern = r"\b" + r"\s+".join(map(re.escape, keyword.split())) + r"\b"
        if re.search(pattern, message, flags=re.IGNORECASE):
            hits.append(keyword)
    return hits


def _fmt(d: date) -> str:
    return d.strftime("%b %d, %Y").replace(" 0", " ")


def _raise_priority(current: Priority, floor: Priority) -> Priority:
    return max(current, floor, key=PRIORITY_ORDER.index)


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------


def evaluate(
    classification: LLMClassification,
    message: str,
    ctx: MemberContext | None,
    rules: Rules | None = None,
    today: date | None = None,
) -> Decision:
    rules = rules or get_rules()
    today = today or rules.today()
    trace = _Trace()

    safety_reasons = _check_safety(classification, message, rules, trace)
    if safety_reasons:
        policy = _Outcome(
            "escalate_safety",
            rules.escalation.safety.queue,
            "Urgent: Trust & Safety agent to contact the member within 24 hours, "
            "advise them to stop wearing the device, and log a product-safety report.",
        )
        trace.add("policy_checks", "policy", "Eligibility checks", "skip", "SAFETY_BYPASS",
                  "Skipped: safety reports go straight to a person; no automated resolution.")
    else:
        policy = _policy_outcome(classification, ctx, rules, today, trace)

    escalation_reasons = _check_escalation(classification, ctx, rules, today, trace)
    if policy.code in HUMAN_REVIEW_OUTCOMES:
        escalation_reasons.append(policy.code)

    if safety_reasons:
        decision, queue, fulfillment = "escalate_safety", policy.queue, None
        next_action = policy.next_action
        escalation_reasons = safety_reasons + escalation_reasons
    elif escalation_reasons and policy.code not in HUMAN_REVIEW_OUTCOMES:
        decision, queue, fulfillment = "escalate_to_human", rules.escalation.queue, None
        next_action = (
            "Human agent to review before anything is sent or shipped. "
            f"Policy recommendation: {policy.next_action}"
        )
    else:
        decision, queue, fulfillment = policy.code, policy.queue, policy.fulfillment
        next_action = policy.next_action

    automated = not escalation_reasons
    priority = _priority(classification, rules, trace, safety=bool(safety_reasons),
                         escalated=not automated)

    reason_codes = [
        r.reason_code for r in trace.results
        if (r.group in ("account", "policy") and r.status in ("pass", "fail"))
        or (r.group in ("safety", "escalation") and r.status == "fail")
    ]

    return Decision(
        decision=decision,
        policy_outcome=policy.code,
        automated=automated,
        escalation_reasons=escalation_reasons,
        assigned_queue=queue,
        priority=priority,
        next_action=next_action,
        reason_codes=reason_codes,
        trace=trace.results,
        facts=policy.facts,
        fulfillment=fulfillment,
        policy_version=rules.policy.version,
        as_of_date=today,
    )


# -----------------------------------------------------------------------------
# 1. Safety
# -----------------------------------------------------------------------------


def _check_safety(clf: LLMClassification, message: str, rules: Rules, trace: _Trace) -> list[str]:
    hits = find_safety_keywords(message, rules.escalation.safety.keywords)
    reasons = []
    if clf.category == "safety_concern":
        reasons.append("safety_ai_category")
    if hits:
        reasons.append("safety_keyword")

    if reasons:
        sources = []
        if "safety_ai_category" in reasons:
            sources.append("the AI classified it as a safety concern")
        if hits:
            sources.append("the message mentions " + ", ".join(f"“{h}”" for h in hits))
        trace.add("safety", "safety", "Safety screen", "fail", "SAFETY_CONCERN",
                  f"Safety signal: {' and '.join(sources)}. Routed to Trust & Safety as urgent.")
    else:
        trace.add("safety", "safety", "Safety screen", "pass", "SAFETY_CLEAR",
                  "No injury, irritation, or overheating signals in the message.")
    return reasons


# -----------------------------------------------------------------------------
# 2. Policy (category-specific eligibility)
# -----------------------------------------------------------------------------


def _policy_outcome(clf, ctx, rules, today, trace) -> _Outcome:
    if clf.category == "billing_membership":
        return _billing(clf, rules, trace)
    if clf.category == "other":
        trace.add("category", "policy", "Policy match", "info", "NO_POLICY_MATCH",
                  "Message doesn't match an automated policy; a support agent will reply.")
        return _Outcome("general_inquiry", rules.troubleshooting_first.queue,
                        "Support agent to read and answer the member's question.")

    if ctx is None:
        trace.add("account", "account", "Account lookup", "fail", "ACCOUNT_NOT_FOUND",
                  "No member account linked to this message, so eligibility can't be checked.")
        return _Outcome("request_account_details", rules.troubleshooting_first.queue,
                        "Ask the member for their account email or order number, then re-triage.")

    m = ctx.member
    trace.add("account", "account", "Account lookup", "pass", "ACCOUNT_FOUND",
              f"{m.name} ({m.member_id}) · {m.country} · {m.plan} plan · "
              f"membership {m.membership_status.replace('_', ' ')}.")

    if clf.category in ("troubleshooting", "warranty_replacement"):
        return _hardware(clf, ctx, rules, today, trace)
    if clf.category == "return_remorse":
        return _return(ctx, rules, today, trace)
    return _shipping(ctx, rules, today, trace)


def _billing(clf, rules, trace) -> _Outcome:
    trace.add("billing_route", "policy", "Billing issues go to the billing team", "pass",
              "BILLING_QUEUE",
              "Billing and membership questions are handled by the billing team; "
              "no return or replacement is created.")
    return _Outcome("route_to_billing", rules.billing.queue,
                    "Billing team to review charges/membership and reply within 1 business day.")


def _hardware(clf, ctx, rules, today, trace) -> _Outcome:
    ts = rules.troubleshooting_first
    issue = clf.sub_category.replace("_", " ")
    needs_troubleshooting = clf.category == "troubleshooting" or clf.sub_category in ts.sub_categories
    already_tried = clf.member_already_troubleshot and ts.skip_if_member_already_troubleshot

    if needs_troubleshooting and not already_tried:
        trace.add("troubleshooting_first", "policy", "Troubleshooting first", "fail",
                  "TROUBLESHOOT_FIRST",
                  f"“{issue}” issues are usually fixable at home, and the member hasn't said "
                  "they've tried the standard steps. Send guided troubleshooting first.")
        return _Outcome("send_troubleshooting", ts.queue,
                        f"Send the guided {issue} troubleshooting steps; if they don't work, "
                        "the member can reply and we'll check replacement eligibility.",
                        facts={"issue": clf.sub_category})
    if needs_troubleshooting:
        trace.add("troubleshooting_first", "policy", "Troubleshooting first", "pass",
                  "TROUBLESHOOTING_DONE",
                  "Member says they already tried the standard steps, so we check warranty eligibility.")
    else:
        trace.add("troubleshooting_first", "policy", "Troubleshooting first", "skip",
                  "TROUBLESHOOTING_NA",
                  f"“{issue}” isn't a troubleshooting-first issue; going straight to warranty checks.")

    return _warranty(ctx, rules, today, trace)


def _warranty(ctx: MemberContext, rules: Rules, today: date, trace: _Trace) -> _Outcome:
    w = rules.warranty
    m = ctx.member
    order = ctx.latest_delivered_order(devices_only=True)
    if order is None:
        trace.add("warranty_period", "policy", "Warranty period", "fail", "NO_DELIVERED_DEVICE",
                  "No delivered PulseBand device found on this account.")
        return _Outcome("no_eligible_order", rules.escalation.queue,
                        "Agent to locate the member's device order before any warranty decision.")

    months = rules.warranty_months_for(m.region)
    expires = order.delivered_date + relativedelta(months=months)
    age_days = (today - order.delivered_date).days
    facts = {
        "order_id": order.order_id,
        "delivered_date": _fmt(order.delivered_date),
        "warranty_months": str(months),
        "warranty_expires": _fmt(expires),
    }
    in_warranty = trace.add(
        "warranty_period", "policy", f"Warranty period ({months} months, {m.region})",
        "pass" if today <= expires else "fail",
        "WARRANTY_ACTIVE" if today <= expires else "WARRANTY_EXPIRED",
        f"Order {order.order_id} delivered {_fmt(order.delivered_date)} ({age_days} days ago). "
        f"{m.region} warranty is {months} months, "
        + (f"valid through {_fmt(expires)}." if today <= expires else f"expired {_fmt(expires)}."),
    )

    status = m.membership_status
    membership_ok = trace.add(
        "membership_active", "policy", "Membership must be active",
        "pass" if status == w.required_membership_status else "fail",
        "MEMBERSHIP_ACTIVE" if status == w.required_membership_status
        else f"MEMBERSHIP_{status.upper()}",
        {
            "active": "Membership is active.",
            "past_due": "Membership is past due. Billing must be resolved before a replacement ships.",
            "cancelled": "Membership is cancelled. Warranty replacements require an active membership.",
        }[status],
    )

    lim = w.replacement_limit
    window_start = today - relativedelta(months=lim.rolling_window_months)
    used = sum(
        1 for c in ctx.prior_cases
        if c.category == "warranty_replacement" and c.outcome == "replacement_shipped"
        and window_start < c.case_date <= today
    )
    under_limit = trace.add(
        "replacement_limit", "policy",
        f"Replacement limit ({lim.max_replacements} per {lim.rolling_window_months} months)",
        "pass" if used < lim.max_replacements else "fail",
        "REPLACEMENT_LIMIT_OK" if used < lim.max_replacements else "REPLACEMENT_LIMIT_REACHED",
        f"{used} warranty replacement(s) since {_fmt(window_start)}; limit is {lim.max_replacements}.",
    )

    if not in_warranty:
        return _Outcome("deny_out_of_warranty", w.queue,
                        "Explain the device is outside warranty and offer the member upgrade/"
                        "discounted replacement options.", facts=facts)
    if not membership_ok:
        action = w.past_due_action if status == "past_due" else w.cancelled_action
        if action == "resolve_billing_first":
            return _Outcome("hold_resolve_billing_first", rules.billing.queue,
                            "Hold the replacement. Ask the member to update payment; once the "
                            "membership is active, the warranty claim can proceed.", facts=facts)
        return _Outcome("deny_membership_inactive", w.queue,
                        "Explain warranty replacements need an active membership and share "
                        "how to reactivate.", facts=facts)
    if not under_limit:
        return _Outcome("manual_review_replacement_limit", rules.escalation.queue,
                        "Warranty specialist to review replacement history before approving.",
                        facts=facts)

    return _Outcome(
        "approve_warranty_replacement", w.queue,
        "Create a warranty RMA: ship a like-for-like replacement and email a prepaid return "
        "label for the faulty device.",
        _plan("warranty_replacement", order, ctx, rules, replacement=True, return_label=True),
        facts=facts,
    )


def _return(ctx: MemberContext, rules: Rules, today: date, trace: _Trace) -> _Outcome:
    r = rules.return_remorse
    order = ctx.latest_delivered_order()
    if order is None:
        trace.add("return_window", "policy", f"Return window ({r.window_days} days)", "fail",
                  "NO_DELIVERED_ORDER",
                  "No delivered order on this account yet, so there's nothing to return.")
        return _Outcome("no_eligible_order", rules.escalation.queue,
                        "Agent to check the order status and help the member cancel if needed.")

    days = (today - order.delivered_date).days
    facts = {
        "order_id": order.order_id,
        "delivered_date": _fmt(order.delivered_date),
        "days_since_delivery": str(days),
        "return_window_days": str(r.window_days),
    }
    ok = trace.add(
        "return_window", "policy", f"Return window ({r.window_days} days)",
        "pass" if days <= r.window_days else "fail",
        "RETURN_WINDOW_OPEN" if days <= r.window_days else "RETURN_WINDOW_CLOSED",
        f"Order {order.order_id} ({order.sku}) delivered {_fmt(order.delivered_date)}, "
        f"{days} days ago. Returns are accepted up to day {r.window_days}.",
    )
    if not ok:
        return _Outcome("deny_return_window_closed", r.queue,
                        f"Explain the {r.window_days}-day return window has passed; mention "
                        "warranty support if the device is faulty.", facts=facts)
    return _Outcome(
        "approve_return", r.queue,
        "Create a return RMA: email a prepaid return label; refund once the device is received.",
        _plan("remorse_return", order, ctx, rules, replacement=False, return_label=True),
        facts=facts,
    )


def _shipping(ctx: MemberContext, rules: Rules, today: date, trace: _Trace) -> _Outcome:
    s = rules.shipping
    order = ctx.latest_order()
    if order is None:
        trace.add("delivery_scan", "policy", "Delivery status", "fail", "NO_ORDER",
                  "No orders found on this account.")
        return _Outcome("no_eligible_order", rules.escalation.queue,
                        "Agent to locate the member's order.")

    if order.delivered_date:
        trace.add("delivery_scan", "policy", "Delivery status", "fail", "DELIVERY_SCAN_EXISTS",
                  f"Order {order.order_id} has a delivery scan on {_fmt(order.delivered_date)}. "
                  "A delivered-but-missing package needs a carrier investigation.")
        return _Outcome("investigate_delivery", s.queue,
                        "Logistics agent to open a carrier trace and contact the member.",
                        facts={"order_id": order.order_id,
                               "delivered_date": _fmt(order.delivered_date)})

    elapsed = int(np.busday_count(order.order_date, today))
    lost = elapsed > s.lost_package_business_days
    eligible_from = np.busday_offset(
        order.order_date, s.lost_package_business_days + 1, roll="forward"
    ).astype(date)
    facts = {
        "order_id": order.order_id,
        "order_date": _fmt(order.order_date),
        "business_days_elapsed": str(elapsed),
        "replacement_eligible_from": _fmt(eligible_from),
    }
    trace.add(
        "lost_package", "policy", f"Lost package (> {s.lost_package_business_days} business days)",
        "pass" if lost else "fail",
        "LOST_PACKAGE_CONFIRMED" if lost else "IN_TRANSIT_WITHIN_SLA",
        f"Order {order.order_id} placed {_fmt(order.order_date)}: {elapsed} business days with no "
        f"delivery scan. Replacement is approved after {s.lost_package_business_days}.",
    )
    if not lost:
        remaining = s.lost_package_business_days - elapsed + 1
        return _Outcome("wait_for_delivery", s.queue,
                        f"Share tracking status; if there's still no delivery scan in "
                        f"{remaining} business day(s), a replacement will be sent.", facts=facts)
    return _Outcome(
        "approve_lost_package_replacement", s.queue,
        "Create a replacement RMA for the lost package (no return label needed) and file a "
        "carrier claim.",
        _plan("lost_package_replacement", order, ctx, rules, replacement=True, return_label=False),
        facts=facts,
    )


def _plan(rma_type, order: Order, ctx: MemberContext, rules: Rules, *, replacement: bool,
          return_label: bool) -> FulfillmentPlan:
    return FulfillmentPlan(
        rma_type=rma_type,
        original_order_id=order.order_id,
        sku=order.sku,
        replacement_sku=order.sku if replacement else None,
        warehouse=rules.routing.region_to_warehouse[ctx.member.region],
        return_label_required=return_label,
        ship_to_country=ctx.member.country,
    )


# -----------------------------------------------------------------------------
# 3. Escalation
# -----------------------------------------------------------------------------


def _check_escalation(clf, ctx, rules, today, trace) -> list[str]:
    e = rules.escalation
    reasons = []

    if not trace.add(
        "confidence", "escalation", f"AI confidence ≥ {e.min_confidence:.2f}",
        "pass" if clf.confidence >= e.min_confidence else "fail",
        "CONFIDENCE_OK" if clf.confidence >= e.min_confidence else "LOW_CONFIDENCE",
        f"The AI is {clf.confidence:.0%} confident in its reading of the message.",
    ):
        reasons.append("low_confidence")

    if ctx is None:
        trace.add("angry_high_value", "escalation", "Angry high-value member", "skip",
                  "NO_ACCOUNT", "No account linked, so plan value is unknown.")
        trace.add("possible_fraud", "escalation", "Possible fraud pattern", "skip",
                  "NO_ACCOUNT", "No account linked, so case history is unknown.")
        return reasons

    ahv = e.angry_high_value
    angry_vip = clf.sentiment in ahv.sentiments and ctx.member.plan in ahv.plans
    if not trace.add(
        "angry_high_value", "escalation", "Angry high-value member",
        "fail" if angry_vip else "pass",
        "ANGRY_HIGH_VALUE" if angry_vip else "SENTIMENT_OK",
        f"Sentiment is {clf.sentiment}; member is on the {ctx.member.plan} plan."
        + (" Angry annual members get a personal reply from an agent." if angry_vip else ""),
    ):
        reasons.append("angry_high_value")

    pf = e.possible_fraud
    since = today - timedelta(days=pf.window_days)
    recent = sum(1 for c in ctx.prior_cases if since <= c.case_date <= today)
    suspicious = recent >= pf.min_prior_cases
    if not trace.add(
        "possible_fraud", "escalation", "Possible fraud pattern",
        "fail" if suspicious else "pass",
        "POSSIBLE_FRAUD" if suspicious else "CASE_HISTORY_OK",
        f"{recent} prior case(s) in the last {pf.window_days} days; "
        f"{pf.min_prior_cases} or more triggers a review.",
    ):
        reasons.append("possible_fraud")

    return reasons


# -----------------------------------------------------------------------------
# 4. Priority
# -----------------------------------------------------------------------------


def _priority(clf, rules, trace, *, safety: bool, escalated: bool) -> Priority:
    base = rules.priority.default_by_category[clf.category]
    priority = _raise_priority(base, clf.urgency)
    notes = [f"category default is {base}"]
    if clf.urgency != base and priority == clf.urgency:
        notes.append(f"raised to {clf.urgency} by the urgency in the message")
    if safety:
        priority = rules.escalation.safety.priority
        notes.append(f"safety concern sets {priority}")
    elif escalated and PRIORITY_ORDER.index(priority) < PRIORITY_ORDER.index("high"):
        priority = "high"
        notes.append("escalated cases are at least high")
    trace.add("priority", "priority", "Priority", "info", f"PRIORITY_{priority.upper()}",
              f"Priority {priority}: " + "; ".join(notes) + ".")
    return priority
