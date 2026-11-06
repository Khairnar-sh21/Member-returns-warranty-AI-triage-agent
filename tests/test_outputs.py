"""Case, RMA, and reply generation — no AI involved."""

import re

import pytest

from conftest import make_clf
from triage import outputs
from triage.classifier import ClassificationResult
from triage.outputs import DECISION_LABELS, format_trace, makes_unapproved_commitment
from triage.pipeline import triage_with_classification
from triage.schemas import DecisionCode

INTERNAL_JARGON = ["fraud", "high-value", "escalat", "manual review", "queue", "reason code",
                   "confidence", "policy_"]


def as_result(clf):
    return ClassificationResult(
        classification=clf, status="ok", attempts=1, provider="test", model="test",
        prompt_version="test", latency_ms=0,
    )


@pytest.fixture
def run(store, rules):
    def _run(member_id, category, sub_category="general", *, message="test message", **kw):
        clf = make_clf(category, sub_category, **kw)
        return triage_with_classification(message, member_id, as_result(clf),
                                          store=store, rules=rules)
    return _run


# --- Case ↔ RMA linkage (CRM/ERP consistency) -------------------------------


def test_warranty_approval_creates_linked_case_and_rma(run):
    r = run("M0001", "warranty_replacement", "charging", tried=True)
    assert r.rma is not None
    assert r.case.rma_id == r.rma.rma_id
    assert r.rma.case_id == r.case.case_id
    assert r.rma.replacement_sku == r.rma.sku
    assert r.rma.warehouse == "US"
    assert r.case.automated and r.case.decision == "approve_warranty_replacement"
    assert r.rma.rma_id in r.reply.body
    assert "approved" in r.reply.subject


def test_no_rma_means_case_has_no_rma_id(run):
    r = run("M0004", "return_remorse")
    assert r.rma is None and r.case.rma_id is None


def test_case_copies_decision_fields(run):
    r = run("M0011", "billing_membership", "double_charge", sentiment="angry")
    assert r.case.decision == r.decision.decision == "escalate_to_human"
    assert r.case.assigned_queue == "human_review"
    assert r.case.sentiment == "angry"
    assert r.case.reason_codes == r.decision.reason_codes
    assert not r.case.automated


def test_ids_are_stable_for_the_same_request(run):
    a = run("M0002", "return_remorse", message="I want to return this")
    b = run("M0002", "return_remorse", message="I want to return this")
    c = run("M0002", "return_remorse", message="Different message")
    assert a.case.case_id == b.case.case_id and a.rma.rma_id == b.rma.rma_id
    assert a.case.case_id != c.case.case_id
    assert re.fullmatch(r"CS-\d{6}-[0-9A-F]{6}", a.case.case_id)


# --- Replies match the decision ---------------------------------------------


def test_return_reply_quotes_window_and_refund(run):
    r = run("M0002", "return_remorse")
    assert "30-day return window" in r.reply.body
    assert "refund" in r.reply.body
    assert r.rma.replacement_sku is None and r.rma.return_label_required


def test_closed_return_window_reply_explains_why_and_offers_warranty(run):
    body = run("M0004", "return_remorse").reply.body
    assert "31 days ago" in body and "30 days" in body
    assert "warranty" in body
    assert "refund" not in body.lower()


def test_out_of_warranty_reply_quotes_expiry(run):
    body = run("M0016", "warranty_replacement", "sensor").reply.body
    assert "12-month warranty ended on Nov 4, 2026" in body


def test_lost_package_reply_needs_no_return(run):
    r = run("M0009", "shipping_delivery", "not_delivered")
    assert r.rma.return_label_required is False
    assert "nothing you need to send back" in r.reply.body


def test_in_transit_reply_gives_the_date_a_replacement_becomes_possible(run):
    r = run("M0010", "shipping_delivery", "not_delivered")
    assert r.decision.facts["replacement_eligible_from"] in r.reply.body
    assert r.rma is None


def test_troubleshooting_reply_has_numbered_steps(run):
    body = run("M0001", "troubleshooting", "charging").reply.body
    assert "1. " in body and "charging contacts" in body


def test_safety_reply_tells_member_to_stop_wearing(run):
    r = run("M0014", "safety_concern", "skin_irritation")
    assert "stop wearing" in r.reply.body
    assert "medical attention" in r.reply.body
    assert r.rma is None


def test_fraud_escalation_reply_reveals_nothing(run):
    r = run("M0012", "warranty_replacement", "sensor")
    assert r.decision.decision == "escalate_to_human"
    assert "fraud" not in r.reply.body.lower()
    assert "approved" not in r.reply.body.lower()


def test_frustrated_member_gets_an_apology(run):
    assert "sorry" in run("M0002", "return_remorse", sentiment="frustrated").reply.body
    assert "sorry" not in run("M0002", "return_remorse").reply.body


def test_reply_without_account_uses_neutral_greeting(store, rules):
    clf = make_clf("return_remorse")
    r = triage_with_classification("return please", None, as_result(clf), store=store, rules=rules)
    assert r.reply.body.startswith("Hi there,")
    assert r.case.member_id is None
    assert r.decision.decision == "request_account_details"


# --- Guardrail: never promise what the rules didn't approve -----------------


@pytest.mark.parametrize("text", [
    "Your refund is on its way",
    "Your replacement is approved",
    "We're sending a new band",
    "We’re sending a new band",
    "Here is your return label",
    "Reference RMA-261105-ABC123",
])
def test_commitment_detector_flags_promises_without_rma(text):
    assert makes_unapproved_commitment(text, rma=None)


def test_guardrail_replaces_a_promising_reply(run, monkeypatch):
    monkeypatch.setattr(outputs, "_compose",
                        lambda *a: ("Approved!", "Good news, your refund is approved."))
    r = run("M0004", "return_remorse")
    assert r.reply.guardrail_triggered
    assert "refund" not in r.reply.body.lower()


# --- Invariants across every persona × category -----------------------------


@pytest.fixture(scope="module")
def every_result(store, rules):
    results = []
    for member_id in list(store.members)[:18] + [None]:
        for category in ["troubleshooting", "warranty_replacement", "return_remorse",
                         "shipping_delivery", "billing_membership", "safety_concern", "other"]:
            for tried in (False, True):
                for sentiment in ("neutral", "angry"):
                    clf = make_clf(category, "charging", tried=tried, sentiment=sentiment)
                    results.append(triage_with_classification(
                        "test", member_id, as_result(clf), store=store, rules=rules))
    return results


def test_templates_never_trip_the_guardrail(every_result):
    assert not any(r.reply.guardrail_triggered for r in every_result)


def test_replies_are_well_formed(every_result):
    for r in every_result:
        body = r.reply.body
        assert body.startswith("Hi ") and body.rstrip().endswith("Member Support team")
        assert "{" not in body and "}" not in body
        prose = body.split("\n\n", 1)[1]
        for word in INTERNAL_JARGON:
            assert word not in prose.lower(), (r.decision.decision, word)


def test_rma_exists_only_when_automated_and_approved(every_result):
    for r in every_result:
        if r.rma:
            assert r.case.automated
            assert r.case.decision.startswith("approve_")


def test_every_decision_has_a_label_and_trace_rows(every_result):
    import typing
    assert set(DECISION_LABELS) == set(typing.get_args(DecisionCode))
    for r in every_result:
        rows = format_trace(r.decision)
        assert len(rows) == len(r.decision.trace)
