"""Rules engine tests — no AI involved.

Each test feeds a hand-written classification plus a synthetic persona's
account data (see data/personas.csv) and checks the deterministic decision.
"""

import pytest

from conftest import make_clf
from triage.rules_engine import evaluate, find_safety_keywords

ALL_CATEGORIES = [
    "troubleshooting", "warranty_replacement", "return_remorse", "shipping_delivery",
    "billing_membership", "safety_concern", "other",
]


# --- Troubleshooting first --------------------------------------------------


def test_charging_issue_gets_troubleshooting_first(triage):
    d = triage("M0001", "warranty_replacement", "charging")
    assert d.decision == "send_troubleshooting"
    assert d.automated and d.fulfillment is None
    assert "TROUBLESHOOT_FIRST" in d.reason_codes


def test_charging_issue_already_troubleshot_gets_warranty_replacement(triage):
    d = triage("M0001", "warranty_replacement", "charging", tried=True)
    assert d.decision == "approve_warranty_replacement"
    assert d.fulfillment.rma_type == "warranty_replacement"
    assert d.fulfillment.replacement_sku == d.fulfillment.sku
    assert d.fulfillment.return_label_required is True
    assert d.fulfillment.warehouse == "US"


def test_non_troubleshooting_defect_skips_straight_to_warranty(triage):
    d = triage("M0001", "warranty_replacement", "cracked_casing")
    assert d.decision == "approve_warranty_replacement"


# --- Return window (30 days, inclusive) -------------------------------------


def test_return_within_window_approved_and_routed_to_eu(triage):
    d = triage("M0002", "return_remorse")
    assert d.decision == "approve_return"
    assert d.fulfillment.rma_type == "remorse_return"
    assert d.fulfillment.replacement_sku is None
    assert d.fulfillment.warehouse == "EU"
    assert d.fulfillment.ship_to_country == "Germany"


def test_return_on_day_30_is_approved(triage):
    assert triage("M0003", "return_remorse").decision == "approve_return"


def test_return_on_day_31_is_denied(triage):
    d = triage("M0004", "return_remorse")
    assert d.decision == "deny_return_window_closed"
    assert d.automated and d.fulfillment is None


# --- Warranty period (12 months, 24 for EU/UK, inclusive) -------------------


def test_uk_member_at_18_months_covered_by_24_month_warranty(triage):
    d = triage("M0005", "warranty_replacement", "strap_broken")
    assert d.decision == "approve_warranty_replacement"
    assert d.fulfillment.warehouse == "EU"


def test_us_member_at_13_months_out_of_warranty(triage):
    assert triage("M0006", "warranty_replacement", "screen").decision == "deny_out_of_warranty"


def test_last_day_of_us_warranty_is_covered(triage):
    assert triage("M0015", "warranty_replacement", "sensor").decision == "approve_warranty_replacement"


def test_us_warranty_expired_yesterday(triage):
    assert triage("M0016", "warranty_replacement", "sensor").decision == "deny_out_of_warranty"


def test_eu_member_at_25_months_out_of_warranty(triage):
    assert triage("M0018", "warranty_replacement", "sensor").decision == "deny_out_of_warranty"


# --- Membership status ------------------------------------------------------


def test_past_due_member_must_resolve_billing_first(triage):
    d = triage("M0007", "warranty_replacement", "sensor")
    assert d.decision == "hold_resolve_billing_first"
    assert d.assigned_queue == "billing"
    assert d.fulfillment is None


def test_cancelled_member_not_eligible_for_warranty(triage):
    d = triage("M0013", "warranty_replacement", "sensor")
    assert d.decision == "deny_membership_inactive"
    assert d.fulfillment is None


# --- Replacement limit ------------------------------------------------------


def test_third_replacement_in_12_months_goes_to_manual_review(triage):
    d = triage("M0008", "warranty_replacement", "sensor")
    assert d.decision == "manual_review_replacement_limit"
    assert not d.automated
    assert d.fulfillment is None
    assert "REPLACEMENT_LIMIT_REACHED" in d.reason_codes


# --- Shipping (> 10 business days without a delivery scan) ------------------


def test_lost_package_after_14_business_days_is_replaced(triage):
    d = triage("M0009", "shipping_delivery", "not_delivered")
    assert d.decision == "approve_lost_package_replacement"
    assert d.fulfillment.return_label_required is False
    assert d.fulfillment.warehouse == "US"  # Canada ships from the US warehouse


def test_package_in_transit_6_business_days_waits(triage):
    assert triage("M0010", "shipping_delivery", "not_delivered").decision == "wait_for_delivery"


def test_package_at_exactly_10_business_days_still_waits(triage):
    assert triage("M0017", "shipping_delivery", "not_delivered").decision == "wait_for_delivery"


def test_delivered_package_reported_missing_needs_investigation(triage):
    d = triage("M0001", "shipping_delivery", "not_received")
    assert d.decision == "investigate_delivery"
    assert not d.automated


# --- Billing ----------------------------------------------------------------


def test_billing_routes_to_billing_queue_never_rma(triage):
    d = triage("M0011", "billing_membership", "double_charge")
    assert d.decision == "route_to_billing"
    assert d.assigned_queue == "billing"
    assert d.fulfillment is None
    assert d.automated


def test_billing_works_without_an_account(store, rules):
    d = evaluate(make_clf("billing_membership", "double_charge"), "", None, rules)
    assert d.decision == "route_to_billing"


# --- Escalation -------------------------------------------------------------


def test_angry_annual_member_escalates_with_policy_recommendation(triage):
    d = triage("M0011", "billing_membership", "double_charge", sentiment="angry")
    assert d.decision == "escalate_to_human"
    assert d.policy_outcome == "route_to_billing"
    assert "angry_high_value" in d.escalation_reasons
    assert d.priority in ("high", "urgent")


def test_angry_monthly_member_is_still_automated(triage):
    d = triage("M0002", "return_remorse", sentiment="angry")
    assert d.decision == "approve_return"
    assert d.automated


def test_three_cases_in_90_days_flags_possible_fraud(triage):
    d = triage("M0012", "warranty_replacement", "sensor")
    assert d.decision == "escalate_to_human"
    assert d.policy_outcome == "approve_warranty_replacement"
    assert "possible_fraud" in d.escalation_reasons
    assert d.fulfillment is None  # nothing ships until a human approves


@pytest.mark.parametrize("confidence, escalated", [(0.69, True), (0.70, False), (0.95, False)])
def test_confidence_threshold(triage, confidence, escalated):
    d = triage("M0002", "return_remorse", confidence=confidence)
    assert (d.decision == "escalate_to_human") is escalated


# --- Safety -----------------------------------------------------------------


def test_safety_category_is_urgent_human_review(triage):
    d = triage("M0014", "safety_concern", "skin_irritation")
    assert d.decision == "escalate_safety"
    assert d.priority == "urgent"
    assert d.assigned_queue == "trust_safety"
    assert not d.automated and d.fulfillment is None


def test_safety_keyword_overrides_ai_misclassification(triage):
    d = triage("M0001", "troubleshooting", "charging",
               message="The band won't charge and now I have a rash under it")
    assert d.decision == "escalate_safety"
    assert "safety_keyword" in d.escalation_reasons


@pytest.mark.parametrize(
    "message, expected",
    [
        ("It's BURNING hot", ["burning"]),
        ("my wrist feels hot to the touch", ["hot to the touch"]),
        ("love the burnished finish", []),
        ("strap is a bit irritating to put on", []),
    ],
)
def test_safety_keywords_match_whole_words(rules, message, expected):
    assert find_safety_keywords(message, rules.escalation.safety.keywords) == expected


# --- Account handling -------------------------------------------------------


def test_unknown_member_is_asked_for_account_details(store, rules):
    d = evaluate(make_clf("return_remorse"), "", None, rules)
    assert d.decision == "request_account_details"
    assert d.fulfillment is None


def test_other_category_goes_to_an_agent(triage):
    d = triage("M0001", "other", "feature_question")
    assert d.decision == "general_inquiry"
    assert not d.automated


# --- Rules come from rules.yaml, not code -----------------------------------


def test_editing_return_window_in_config_changes_decision(triage, rules):
    longer = rules.model_copy(
        update={"return_remorse": rules.return_remorse.model_copy(update={"window_days": 31})}
    )
    assert triage("M0004", "return_remorse").decision == "deny_return_window_closed"
    assert triage("M0004", "return_remorse", rules_override=longer).decision == "approve_return"


def test_editing_confidence_threshold_changes_escalation(triage, rules):
    stricter = rules.model_copy(
        update={"escalation": rules.escalation.model_copy(update={"min_confidence": 0.95})}
    )
    assert triage("M0002", "return_remorse", confidence=0.9).automated
    assert not triage("M0002", "return_remorse", confidence=0.9, rules_override=stricter).automated


# --- Invariants across every persona × category -----------------------------


@pytest.fixture(scope="module")
def every_decision(store, rules):
    results = []
    for member_id in list(store.members)[:18] + [None]:
        ctx = store.get_context(member_id)
        for category in ALL_CATEGORIES:
            for tried in (False, True):
                for sentiment in ("neutral", "angry"):
                    clf = make_clf(category, "charging", tried=tried, sentiment=sentiment)
                    results.append((clf, evaluate(clf, "", ctx, rules)))
    return results


def test_every_decision_has_trace_and_next_action(every_decision):
    for _, d in every_decision:
        assert d.trace and d.next_action and d.assigned_queue


def test_escalated_cases_never_carry_an_rma(every_decision):
    for _, d in every_decision:
        if not d.automated:
            assert d.fulfillment is None


def test_billing_never_produces_an_rma(every_decision):
    for clf, d in every_decision:
        if clf.category == "billing_membership":
            assert d.fulfillment is None


def test_engine_is_deterministic(store, rules):
    clf = make_clf("warranty_replacement", "charging", tried=True)
    ctx = store.get_context("M0001")
    assert evaluate(clf, "x", ctx, rules) == evaluate(clf, "x", ctx, rules)
