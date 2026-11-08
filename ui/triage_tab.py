"""Triage tab: request form, then the results view (per the UI concept)."""

from __future__ import annotations

import json
import logging
from functools import lru_cache

import pandas as pd
import streamlit as st

from triage.config import DATA_DIR, get_rules
from triage.data import MemberContext, get_store
from triage.demo import cached_classification, load_cache, load_scenarios
from triage.outputs import DECISION_LABELS
from triage.pipeline import TriageResult, run_triage, triage_with_classification
from triage.rules_engine import recent_replacements, warranty_expiry
from ui import session
from ui.components import (
    CATEGORY_LABELS,
    QUEUE_LABELS,
    esc,
    html,
    humanize,
    info_box,
    kv_rows,
    metric_card,
    outcome_pill,
    page_heading,
    status_pill,
    trace_row,
)
from ui.settings import MAX_MESSAGE_CHARS
from ui.styles import OUTCOME_COLORS

log = logging.getLogger(__name__)

NO_ACCOUNT = "__none__"


@lru_cache(maxsize=1)
def _persona_notes() -> dict[str, str]:
    df = pd.read_csv(DATA_DIR / "personas.csv")
    return dict(zip(df.member_id, df.scenario_note))


def _scenario(sid: str | None):
    return next((s for s in load_scenarios() if s.id == sid), None)


# -----------------------------------------------------------------------------
# State + callbacks
# -----------------------------------------------------------------------------


def _init_form() -> None:
    # Streamlit drops widget state when a widget isn't drawn (e.g. on the results
    # view); re-assigning keeps the form filled in for "New request".
    for key in ("message", "member", "scenario"):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]
    if "scenario" not in st.session_state:
        first = load_scenarios()[0]
        st.session_state.scenario = first.id
        st.session_state.message = first.message
        st.session_state.member = first.member_id


def _on_scenario() -> None:
    s = _scenario(st.session_state.scenario)
    if s:
        st.session_state.message = s.message
        st.session_state.member = s.member_id


def _on_edit() -> None:
    s = _scenario(st.session_state.get("scenario"))
    if s and st.session_state.message.strip() != s.message:
        st.session_state.scenario = None


def _on_clear() -> None:
    st.session_state.message = ""
    st.session_state.scenario = None
    st.session_state.notice = None


def _on_new_request() -> None:
    st.session_state.result = None
    st.session_state.notice = None


def _run() -> None:
    message = st.session_state.message.strip()
    member_id = None if st.session_state.member == NO_ACCOUNT else st.session_state.member
    st.session_state.notice = None
    if not message:
        st.session_state.notice = ("warning", "Type a member message or pick a sample scenario first.")
        return

    try:
        if session.is_live():
            blocked = session.try_consume_live_call()
            if blocked:
                st.session_state.notice = ("warning", blocked)
                return
            result = run_triage(message, member_id, session.provider())
            if result.classification.status == "fallback":
                st.session_state.notice = (
                    "warning",
                    f"{result.classification.error} The rules sent this case to a person, "
                    "which is the safe default when the AI can't be used.",
                )
        else:
            if load_cache() is None:
                st.session_state.notice = ("error", "The demo cache hasn't been built yet.")
                return
            classification = cached_classification(message)
            if classification is None:
                hint = ("switch to Live mode to triage your own message."
                        if session.live_available()
                        else "live mode isn't enabled on this deployment.")
                st.session_state.notice = (
                    "info",
                    "Demo mode replays cached AI results for the 10 sample scenarios only. "
                    f"Pick a sample above, or {hint}",
                )
                return
            result = triage_with_classification(message, member_id, classification, mode="demo")
        session.record(result)
    except Exception:
        log.exception("Triage failed")
        st.session_state.notice = ("error", "Something went wrong while triaging this request. "
                                             "Please try again.")


# -----------------------------------------------------------------------------
# Form view
# -----------------------------------------------------------------------------


def _member_label(member_id: str) -> str:
    if member_id == NO_ACCOUNT:
        return "No account linked (free text only)"
    m = get_store().members[member_id]
    return f"{m.name} · {m.member_id} · {m.country}"


def _member_card(ctx: MemberContext) -> None:
    rules = get_rules()
    today = rules.today()
    m = ctx.member
    device = ctx.latest_delivered_order(devices_only=True)
    latest = ctx.latest_order()
    used, _ = recent_replacements(ctx, rules, today)
    recent_cases = sum(
        1 for c in ctx.prior_cases
        if (today - c.case_date).days <= rules.escalation.possible_fraud.window_days
    )

    rows = [
        ("Member ID", m.member_id),
        ("Country / region", f"{m.country} ({m.region})"),
        ("Plan", m.plan.capitalize()),
        ("Member since", f"{m.membership_start_date:%b %d, %Y}"),
    ]
    if latest and latest.delivered_date is None:
        rows += [("Latest order", f"{latest.sku} · in transit"),
                 ("Ordered", f"{latest.order_date:%b %d, %Y}")]
    if device:
        rows += [("Device SKU", device.sku),
                 ("Delivered", f"{device.delivered_date:%b %d, %Y}"),
                 ("Days since delivery", str((today - device.delivered_date).days))]
    rows += [
        (f"Replacements ({rules.warranty.replacement_limit.rolling_window_months} mo)",
         f"{used} of {rules.warranty.replacement_limit.max_replacements}"),
        (f"Cases (last {rules.escalation.possible_fraud.window_days} days)", str(recent_cases)),
    ]

    if device:
        expires = warranty_expiry(device, m.region, rules)
        months = rules.warranty_months_for(m.region)
        total = (expires - device.delivered_date).days
        left = (expires - today).days
        regional = " (EU/UK)" if m.region in rules.warranty.months_by_region else ""
        note = (f"Warranty: {left} of {total} days remaining · {months}-month{regional}"
                if left >= 0 else f"Warranty: expired {expires:%b %d, %Y} · {months}-month{regional}")
    else:
        note = "Warranty starts when the device is delivered."

    html(
        '<div class="pb-card" style="padding:22px 24px">'
        '<div class="pb-card-head" style="align-items:flex-start;margin-bottom:12px">'
        '<div><div class="pb-label" style="font-size:13px;font-weight:500">Member account</div>'
        f'<div style="font-size:22px;font-weight:600">{esc(m.name)}</div></div>'
        f'{status_pill(m.membership_status)}</div>'
        f'{kv_rows(rows)}'
        f'<div class="pb-note" style="margin-top:14px">{esc(note)}</div></div>'
    )


def _render_form() -> None:
    page_heading("Triage a request",
                 "Pick a synthetic member and describe the problem. "
                 "The AI reads the message; the rules engine makes the call.")
    st.write("")
    left, right = st.columns([5, 7], gap="large")

    with left:
        options = list(get_store().members) + [NO_ACCOUNT]
        st.selectbox("Select a member", options, key="member", format_func=_member_label)
        member_id = st.session_state.member
        if member_id in _persona_notes():
            st.caption(f"Test persona: {_persona_notes()[member_id]}")
        ctx = get_store().get_context(None if member_id == NO_ACCOUNT else member_id)
        if ctx:
            _member_card(ctx)
        else:
            html(info_box("No account is linked, so the rules can't check eligibility. "
                          "Billing and safety messages are still routed; everything else "
                          "asks the member for their account details."))

    with right:
        st.text_area("Member message", key="message", height=150, max_chars=MAX_MESSAGE_CHARS,
                     on_change=_on_edit)
        scenarios = load_scenarios()
        st.pills(
            "Or load a sample scenario",
            options=[s.id for s in scenarios],
            format_func=lambda sid: _scenario(sid).label,
            key="scenario",
            on_change=_on_scenario,
        )

        b1, b2, caption = st.columns([1.2, 1, 4], vertical_alignment="center")
        run_clicked = b1.button("Run triage", type="primary", width="stretch")
        b2.button("Clear", on_click=_on_clear, width="stretch")
        if session.is_live():
            caption.caption(f"Live mode · uses 1 of {session.session_remaining()} remaining calls")
        else:
            caption.caption("Demo mode · replays a cached AI response")

        if run_clicked:
            label = ("Reading the message with AI, then applying policy rules…"
                     if session.is_live() else "Applying policy rules…")
            with st.spinner(label):
                _run()
            if st.session_state.result is not None:
                st.rerun()

        _render_notice()
        html(info_box(
            "<b>What happens next:</b> the AI returns category, sentiment, urgency and confidence "
            "as JSON. Versioned policy rules then decide the outcome and generate the CRM case, "
            "any RMA, and a drafted reply."
        ))


def _render_notice() -> None:
    notice = st.session_state.get("notice")
    if notice:
        kind, text = notice
        {"info": st.info, "warning": st.warning, "error": st.error}[kind](text)


# -----------------------------------------------------------------------------
# Results view
# -----------------------------------------------------------------------------

OUTCOME_SUBTEXT = {
    "automated": "No human review needed",
    "needs_review": "Queue: {queue}",
    "escalated": "Queue: {queue}",
}

REPLY_NOTES = {
    "automated": "Would be sent automatically · template filled from the rules' facts",
    "needs_review": "Draft held for agent approval · not sent",
    "escalated": "Draft held for agent approval · not sent",
}


def _render_results(r: TriageResult) -> None:
    rules = get_rules()
    clf = r.classification.classification
    d, case = r.decision, r.case
    store = get_store()
    member = store.members.get(r.member_id) if r.member_id else None
    out = OUTCOME_COLORS[case.outcome]

    who = f"{member.name} · {member.member_id} · {member.country}" if member else "No account linked"
    req_col, btn_col = st.columns([6, 1], vertical_alignment="center")
    req_col.html(
        '<div class="pb-request"><span class="pb-faint">▸</span>'
        '<span style="font-weight:600;white-space:nowrap">Request</span>'
        f'<span class="pb-ellipsis">{esc(who)} · “{esc(r.message)}”</span></div>'
    )
    btn_col.button("New request", on_click=_on_new_request, width="stretch")
    _render_notice()

    timing = (f"{r.classification.latency_ms / 1000:.1f} s" if r.mode == "live"
              else "cached AI response")
    html(
        '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;'
        'margin-top:8px"><div class="pb-title">Triage result</div>'
        f'<div class="pb-mono pb-muted" style="font-size:14px">{esc(case.case_id)} · '
        f'{case.created_at:%d %b %Y, %H:%M} UTC · {esc(timing)}</div></div>'
    )

    # -- summary cards ---------------------------------------------------------
    threshold = rules.escalation.min_confidence
    above = clf.confidence >= threshold
    queue = QUEUE_LABELS.get(d.assigned_queue, d.assigned_queue)
    if d.decision == "escalate_safety":
        outcome_sub = f"{queue} · urgent"
    else:
        outcome_sub = OUTCOME_SUBTEXT[case.outcome].format(queue=queue)
    cards = st.columns(4)
    cards[0].html(metric_card("Category", esc(CATEGORY_LABELS[clf.category]),
                              humanize(clf.sub_category)))
    cards[1].html(metric_card(
        "Confidence", f"{clf.confidence:.2f}",
        f"{'↑ above' if above else '↓ below'} {threshold:.2f} threshold",
        "#1D6B3F" if above else "#8A5300",
    ))
    cards[2].html(metric_card("Sentiment", esc(clf.sentiment.capitalize()),
                              f"Urgency: {clf.urgency}"))
    cards[3].html(metric_card("Outcome", outcome_pill(case.outcome, 18), outcome_sub))

    # -- AI understanding + decision trace ---------------------------------------
    ai_col, rules_col = st.columns([5, 7], gap="medium")
    facts = [("Issue", humanize(clf.sub_category)),
             ("Already troubleshot", "Yes" if clf.member_already_troubleshot else "No"),
             ("Urgency", clf.urgency.capitalize())]
    facts += [(humanize(k), str(v)) for k, v in clf.extracted_facts.items() if v not in (None, "")]
    model_line = (f"{r.classification.provider} · {r.classification.model} · "
                  f"{r.classification.prompt_version} · {r.classification.status}")
    if r.mode == "demo":
        model_line += " · replayed from cache"
    ai_col.html(
        '<div class="pb-card"><div class="pb-card-head" style="margin-bottom:10px">'
        '<div class="pb-h">AI Understanding</div>'
        '<span class="pb-pill pb-chip-ai">AI · probabilistic</span></div>'
        f'{kv_rows(facts)}'
        '<div class="pb-note" style="margin-top:12px;color:#1B2228">'
        '<div class="pb-faint" style="font-weight:600;letter-spacing:.05em;text-transform:uppercase;'
        'margin-bottom:4px">Reasoning</div>'
        f'<div style="font-size:15px;line-height:1.5">{esc(clf.reasoning_summary)}</div></div>'
        f'<div class="pb-faint pb-mono" style="margin-top:10px">{esc(model_line)}</div></div>'
    )

    rules_col.html(
        '<div class="pb-card-strong"><div class="pb-card-head">'
        '<div class="pb-h">Decision Trace</div>'
        f'<span class="pb-pill pb-chip-rules">Rules · deterministic · {esc(d.policy_version)}</span>'
        '</div><div class="pb-muted" style="font-size:14px;padding:4px 0 6px">'
        'Evaluated top to bottom. Same inputs always produce the same decision.</div>'
        + "".join(trace_row(t) for t in d.trace) +
        f'<div style="padding:14px 16px;margin-top:6px;border-radius:8px;background:{out["bg"]};'
        f'border:1px solid {out["line"]};color:{out["fg"]}">'
        '<div style="display:flex;gap:12px;align-items:baseline">'
        '<div style="font-size:15px;font-weight:700;white-space:nowrap">→ Decision</div>'
        f'<div style="font-size:16px;font-weight:600">{esc(DECISION_LABELS[d.decision])}</div></div>'
        f'<div style="font-size:14px;margin-top:4px;opacity:.9">{esc(d.next_action)}</div>'
        '</div></div>'
    )

    # -- outputs ---------------------------------------------------------------
    case_col, rma_col, reply_col = st.columns(3, gap="medium")
    with case_col.container(key="pbcard_case"):
        html('<div class="pb-card-head"><div class="pb-h-sm">CRM Case</div>'
             '<div class="pb-faint pb-mono">case.json</div></div>')
        st.code(json.dumps(case.model_dump(mode="json"), indent=2), language="json", wrap_lines=True)

    with rma_col.container(key="pbcard_rma"):
        html('<div class="pb-card-head"><div class="pb-h-sm">RMA / Replacement Order</div>'
             '<div class="pb-faint pb-mono">rma.json</div></div>')
        if r.rma:
            st.code(json.dumps(r.rma.model_dump(mode="json"), indent=2), language="json", wrap_lines=True)
        else:
            html(info_box(esc(_no_rma_note(r))))

    with reply_col.container(key="pbcard_reply"):
        html('<div class="pb-card-head"><div class="pb-h-sm">Drafted Member Reply</div></div>')
        to = member.email if member else "(no account linked)"
        html(
            '<div class="pb-email"><div class="pb-email-head">'
            f'<div>To: {esc(to)}</div>'
            f'<div style="font-size:15px;font-weight:600;color:#1B2228;margin-top:3px">'
            f'{esc(r.reply.subject)}</div></div>'
            f'<div class="pb-email-body">{esc(r.reply.body)}</div></div>'
        )
        note = ("Safety guidance sent immediately · case stays open with Trust & Safety"
                if d.decision == "escalate_safety" else REPLY_NOTES[case.outcome])
        if r.reply.guardrail_triggered:
            note = "Guardrail replaced a draft that promised something the rules didn't approve"
        html(f'<div class="pb-faint" style="margin-top:8px">{esc(note)}</div>')


def _no_rma_note(r: TriageResult) -> str:
    d = r.decision
    if d.policy_outcome.startswith("approve_") and not d.automated:
        return ("No RMA yet. Policy would approve one, but nothing ships until a person "
                "reviews this case.")
    if d.decision == "escalate_safety":
        return "No RMA. Trust & Safety decides on any return-for-inspection after review."
    if r.classification.classification.category == "billing_membership":
        return "No RMA. Billing issues never create a return or replacement."
    return "No RMA created. The rules didn't approve a return or replacement for this request."


# -----------------------------------------------------------------------------


def render() -> None:
    _init_form()
    result = st.session_state.get("result")
    if result is None:
        _render_form()
    else:
        _render_results(result)
