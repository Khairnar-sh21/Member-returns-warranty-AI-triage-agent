"""Turn a rules-engine Decision into the records a real support org would create.

  build_case   → CRM support case
  build_rma    → ERP return/replacement order (only when rules approved one)
  build_reply  → drafted member reply
  format_trace → decision trace rows for the UI

Replies are written from templates, not by the AI, so their content can only
reflect what the rules decided. A final guardrail blocks any reply that makes
a commitment (refund, replacement, return label) when no RMA was approved.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from triage.data import MemberContext
from triage.schemas import (
    Decision,
    LLMClassification,
    MemberReply,
    RMAOrder,
    RuleResult,
    SupportCase,
)

SIGN_OFF = "Warmly,\nThe PulseBand Member Support team"

WAREHOUSE_LABELS = {"US": "US", "EU": "European", "APAC": "Asia-Pacific"}

DECISION_LABELS = {
    "send_troubleshooting": "Send troubleshooting steps",
    "approve_warranty_replacement": "Warranty replacement approved",
    "deny_out_of_warranty": "Not eligible: outside warranty",
    "deny_membership_inactive": "Not eligible: membership inactive",
    "hold_resolve_billing_first": "On hold: resolve billing first",
    "manual_review_replacement_limit": "Manual review: replacement limit reached",
    "approve_return": "Return approved",
    "deny_return_window_closed": "Not eligible: return window closed",
    "approve_lost_package_replacement": "Lost-package replacement approved",
    "wait_for_delivery": "Still in transit: wait for delivery",
    "investigate_delivery": "Carrier investigation needed",
    "route_to_billing": "Routed to billing team",
    "general_inquiry": "General inquiry: agent to reply",
    "request_account_details": "Ask member for account details",
    "no_eligible_order": "No eligible order found",
    "escalate_safety": "Urgent safety review",
    "escalate_to_human": "Escalated to a human agent",
}

TROUBLESHOOTING_STEPS = {
    "charging": [
        "Wipe the gold charging contacts on the back of the band and on the charger with a dry cloth.",
        "Seat the band firmly on the charger and check the light comes on within 10 seconds.",
        "Try a different USB wall adapter (not a laptop port) and leave it for 30 minutes.",
        "Restart the band by holding the side button for 15 seconds.",
    ],
    "sync": [
        "Open the PulseBand app and keep it in the foreground for a minute.",
        "Make sure the app is updated to the latest version.",
        "Turn your phone's Bluetooth off and on again, then reopen the app.",
        "Restart the band by holding the side button for 15 seconds.",
    ],
    "bluetooth": [
        "In your phone's Bluetooth settings, choose “Forget this device” for your PulseBand.",
        "Restart your phone, then restart the band by holding the side button for 15 seconds.",
        "Re-pair from the PulseBand app (Settings → Devices → Pair new band), keeping the band close.",
    ],
    "default": [
        "Make sure the PulseBand app is updated to the latest version.",
        "Restart your phone, then restart the band by holding the side button for 15 seconds.",
        "Charge the band for at least 30 minutes and check whether the issue continues.",
    ],
}

# Words that commit the company to something. Only allowed when an RMA exists.
COMMITMENT_PATTERNS = [
    r"\bapproved\b",
    r"\bwe(?:'|’)re sending\b",
    r"\breturn label\b",
    r"\brefund\b",
    r"\bRMA-",
]

GENERIC_HOLDING_REPLY = (
    "Thanks for getting in touch. A member of our support team is reviewing your request "
    "personally and will get back to you soon."
)


# -----------------------------------------------------------------------------
# IDs
# -----------------------------------------------------------------------------


def _short_id(*parts: object) -> str:
    """Stable 6-character suffix, so re-running the same request gives the same IDs."""
    digest = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return digest[:6].upper()


def make_ids(message: str, member_id: str | None, decision: Decision) -> tuple[str, str]:
    suffix = _short_id(member_id, message.strip(), decision.as_of_date)
    stamp = decision.as_of_date.strftime("%y%m%d")
    return f"CS-{stamp}-{suffix}", f"RMA-{stamp}-{suffix}"


# -----------------------------------------------------------------------------
# Case + RMA
# -----------------------------------------------------------------------------


def build_case(
    *,
    case_id: str,
    rma_id: str | None,
    member_id: str | None,
    classification: LLMClassification,
    decision: Decision,
    channel: str = "web_form",
    created_at: datetime | None = None,
) -> SupportCase:
    return SupportCase(
        case_id=case_id,
        member_id=member_id,
        channel=channel,
        category=classification.category,
        sub_category=classification.sub_category,
        priority=decision.priority,
        sentiment=classification.sentiment,
        decision=decision.decision,
        reason_codes=decision.reason_codes,
        next_action=decision.next_action,
        assigned_queue=decision.assigned_queue,
        automated=decision.automated,
        rma_id=rma_id,
        policy_version=decision.policy_version,
        created_at=created_at or datetime.now(timezone.utc).replace(microsecond=0),
    )


def build_rma(*, rma_id: str, case_id: str, decision: Decision) -> RMAOrder | None:
    plan = decision.fulfillment
    if plan is None:
        return None
    return RMAOrder(rma_id=rma_id, case_id=case_id, **plan.model_dump())


# -----------------------------------------------------------------------------
# Member reply
# -----------------------------------------------------------------------------


def _opener(sentiment: str) -> str:
    if sentiment in ("angry", "frustrated"):
        return ("I'm really sorry you're dealing with this. I know it's frustrating, "
                "and I want to get it sorted for you.")
    return "Thanks for reaching out."


def _steps(issue: str) -> str:
    steps = TROUBLESHOOTING_STEPS.get(issue, TROUBLESHOOTING_STEPS["default"])
    return "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))


def _compose(decision: Decision, rma: RMAOrder | None, sentiment: str) -> tuple[str, str]:
    f = decision.facts
    opener = _opener(sentiment)
    warehouse = WAREHOUSE_LABELS.get(rma.warehouse, rma.warehouse) if rma else ""

    match decision.decision:
        case "send_troubleshooting":
            issue = f.get("issue", "general")
            label = issue.replace("_", " ")
            return (
                f"Let's get your PulseBand {label} issue fixed",
                f"{opener} Most {label} issues can be fixed in a few minutes. "
                f"Please try these steps:\n\n{_steps(issue)}\n\n"
                "If it's still not working afterwards, just reply to this email and tell us "
                "which steps you tried. We'll then check your replacement options.",
            )
        case "approve_warranty_replacement":
            return (
                "Your PulseBand warranty replacement is approved",
                f"{opener} Good news: your band is covered by its {f['warranty_months']}-month "
                f"warranty (valid through {f['warranty_expires']}), so we're sending you a "
                f"replacement {rma.replacement_sku} from our {warehouse} warehouse. "
                f"Your reference is {rma.rma_id}.\n\n"
                "You'll also get a prepaid return label by email. Please use it to send the "
                "original band back once your replacement arrives.",
            )
        case "approve_return":
            return (
                "Your PulseBand return is approved",
                f"{opener} Your order {f['order_id']} was delivered on {f['delivered_date']}, "
                f"which is within our {f['return_window_days']}-day return window. "
                f"Your return reference is {rma.rma_id}.\n\n"
                "You'll get a prepaid return label by email. Once the band reaches our "
                f"{warehouse} returns center, we'll process your refund.",
            )
        case "approve_lost_package_replacement":
            return (
                "We're sending a replacement for your missing order",
                f"{opener} Your order {f['order_id']} (placed {f['order_date']}) still has no "
                f"delivery scan after {f['business_days_elapsed']} business days, so we're "
                f"sending a replacement from our {warehouse} warehouse. Your reference is "
                f"{rma.rma_id}. There's nothing you need to send back.",
            )
        case "wait_for_delivery":
            return (
                "An update on your PulseBand order",
                f"{opener} Your order {f['order_id']} was placed on {f['order_date']} and is "
                f"still in transit ({f['business_days_elapsed']} business days so far). "
                "Packages sometimes take a little longer than expected.\n\n"
                f"If it hasn't arrived by {f['replacement_eligible_from']}, reply to this email "
                "and we'll look into a replacement for you.",
            )
        case "investigate_delivery":
            return (
                "We're looking into your delivery",
                f"{opener} Our tracking shows order {f['order_id']} as delivered on "
                f"{f['delivered_date']}, so I've asked our logistics team to open an "
                "investigation with the carrier. They'll be in touch with you soon.",
            )
        case "route_to_billing":
            return (
                "Your billing question is with our billing team",
                f"{opener} I've passed your message to our billing team. They can see your "
                "full payment history, will review the charges on your account, and will reply "
                "to you directly.",
            )
        case "hold_resolve_billing_first":
            return (
                "One quick step before we can help with your PulseBand",
                f"{opener} Your warranty request is on hold because there's an outstanding "
                "balance on your membership. Once you've updated your payment details in the "
                "app (Settings → Membership → Payment), reply here and we'll pick your request "
                "back up.",
            )
        case "deny_membership_inactive":
            return (
                "About your PulseBand warranty request",
                f"{opener} Warranty replacements are part of an active PulseBand membership. "
                "Your membership is currently cancelled, so we can't send a replacement under "
                "warranty. If you reactivate your membership in the app, reply here and we'll "
                "take another look.",
            )
        case "deny_out_of_warranty":
            return (
                "About your PulseBand warranty request",
                f"{opener} Your band was delivered on {f['delivered_date']}, and its "
                f"{f['warranty_months']}-month warranty ended on {f['warranty_expires']}, so it "
                "isn't covered for a free replacement. I'm sorry that's not the answer you were "
                "hoping for. You can see current upgrade options in the PulseBand app under "
                "Membership.",
            )
        case "deny_return_window_closed":
            return (
                "About your PulseBand return request",
                f"{opener} Your order {f['order_id']} was delivered on {f['delivered_date']}, "
                f"{f['days_since_delivery']} days ago. Our change-of-mind return window is "
                f"{f['return_window_days']} days, so this order is no longer eligible for a "
                "return.\n\nIf something is actually wrong with the band, reply and tell us "
                "what's happening. It may be covered by your warranty.",
            )
        case "request_account_details":
            return (
                "Can you help us find your account?",
                f"{opener} To look into this, we need to find your PulseBand account. Please "
                "reply with the email address on your membership or your order number "
                "(it starts with SO-).",
            )
        case "escalate_safety":
            return (
                "Your safety comes first: we're on it",
                "Thank you for telling us, and I'm sorry this happened. Please stop wearing "
                "your band until we've been in touch. If you have a severe reaction, a burn, or "
                "symptoms that are getting worse, please seek medical attention.\n\n"
                "A specialist from our Trust & Safety team is reviewing your report as a "
                "priority and will contact you directly.",
            )
        case _:
            # escalate_to_human, manual_review_*, general_inquiry, no_eligible_order.
            # Deliberately says nothing about why (e.g. a fraud check).
            return "We've received your message", f"{opener} {GENERIC_HOLDING_REPLY}"


def makes_unapproved_commitment(text: str, rma: RMAOrder | None) -> bool:
    if rma is not None:
        return False
    return any(re.search(p, text, flags=re.IGNORECASE) for p in COMMITMENT_PATTERNS)


def build_reply(
    *,
    decision: Decision,
    rma: RMAOrder | None,
    classification: LLMClassification,
    ctx: MemberContext | None,
) -> MemberReply:
    first_name = ctx.member.name.split()[0] if ctx else None
    greeting = f"Hi {first_name}," if first_name else "Hi there,"

    subject, body = _compose(decision, rma, classification.sentiment)
    guardrail = makes_unapproved_commitment(f"{subject}\n{body}", rma)
    if guardrail:
        subject, body = "We've received your message", GENERIC_HOLDING_REPLY

    return MemberReply(
        subject=subject,
        body=f"{greeting}\n\n{body}\n\n{SIGN_OFF}",
        guardrail_triggered=guardrail,
    )


# -----------------------------------------------------------------------------
# Decision trace for display
# -----------------------------------------------------------------------------

GROUP_LABELS = {
    "safety": "Safety",
    "account": "Account",
    "policy": "Policy",
    "escalation": "Escalation",
    "priority": "Priority",
}


def _status_label(result: RuleResult) -> tuple[str, str]:
    if result.status == "pass":
        return "✅", "Passed"
    if result.status == "fail":
        triggered = result.group in ("safety", "escalation")
        return ("⚠️", "Triggered") if triggered else ("❌", "Not met")
    if result.status == "info":
        return "ℹ️", "Info"
    return "➖", "Not applicable"


def format_trace(decision: Decision) -> list[dict[str, str]]:
    rows = []
    for r in decision.trace:
        icon, label = _status_label(r)
        rows.append({
            "": icon,
            "Stage": GROUP_LABELS[r.group],
            "Rule": r.name,
            "Result": label,
            "Why": r.detail,
            "Code": r.reason_code,
        })
    return rows
