"""End-to-end triage: message → AI classification → rules → case / RMA / reply.

This is the single entry point used by the UI, the demo cache, and the eval.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from triage.classifier import ClassificationResult, classify
from triage.config import Rules, get_rules
from triage.data import DataStore, get_store
from triage.llm import LLMProvider
from triage.outputs import build_case, build_reply, build_rma, make_ids
from triage.rules_engine import evaluate
from triage.schemas import Decision, MemberReply, RMAOrder, SupportCase


class TriageResult(BaseModel):
    message: str
    member_id: str | None
    mode: Literal["live", "demo"]
    classification: ClassificationResult
    decision: Decision
    case: SupportCase
    rma: RMAOrder | None
    reply: MemberReply


def triage_with_classification(
    message: str,
    member_id: str | None,
    classification: ClassificationResult,
    *,
    mode: Literal["live", "demo"] = "live",
    channel: str = "web_form",
    store: DataStore | None = None,
    rules: Rules | None = None,
    created_at: datetime | None = None,
) -> TriageResult:
    """Everything after the AI step. Deterministic for a given classification."""
    store = store or get_store()
    rules = rules or get_rules()
    ctx = store.get_context(member_id)
    member_id = ctx.member.member_id if ctx else None
    clf = classification.classification

    decision = evaluate(clf, message, ctx, rules)
    case_id, rma_id = make_ids(message, member_id, decision)
    rma = build_rma(rma_id=rma_id, case_id=case_id, decision=decision)
    case = build_case(
        case_id=case_id,
        rma_id=rma.rma_id if rma else None,
        member_id=member_id,
        classification=clf,
        decision=decision,
        channel=channel,
        created_at=created_at,
    )
    reply = build_reply(decision=decision, rma=rma, classification=clf, ctx=ctx)

    return TriageResult(
        message=message,
        member_id=member_id,
        mode=mode,
        classification=classification,
        decision=decision,
        case=case,
        rma=rma,
        reply=reply,
    )


def run_triage(
    message: str,
    member_id: str | None,
    provider: LLMProvider,
    **kwargs,
) -> TriageResult:
    classification = classify(message, provider)
    return triage_with_classification(message, member_id, classification, mode="live", **kwargs)
