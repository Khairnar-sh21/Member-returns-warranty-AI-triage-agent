"""Small HTML building blocks. Every dynamic value goes through esc()."""

from __future__ import annotations

from html import escape

import streamlit as st

from triage.schemas import RuleResult
from ui.styles import OUTCOME_COLORS, STATUS_ICONS

CATEGORY_LABELS = {
    "troubleshooting": "Troubleshooting",
    "warranty_replacement": "Warranty replacement",
    "return_remorse": "Return",
    "shipping_delivery": "Shipping / delivery",
    "billing_membership": "Billing / membership",
    "safety_concern": "Safety concern",
    "other": "Other",
}

QUEUE_LABELS = {
    "tier1_support": "Tier 1 support",
    "warranty_ops": "Warranty ops",
    "returns_ops": "Returns ops",
    "logistics": "Logistics",
    "billing": "Billing team",
    "trust_safety": "Trust & Safety",
    "human_review": "Human review",
}


def esc(value: object) -> str:
    return escape(str(value), quote=True)


def humanize(snake: str) -> str:
    return snake.replace("_", " ").strip().capitalize()


def html(markup: str) -> None:
    st.html(markup)


def outcome_pill(outcome: str, size: int = 13) -> str:
    c = OUTCOME_COLORS[outcome]
    return (f'<span class="pb-pill" style="background:{c["bg"]};color:{c["fg"]};'
            f'font-size:{size}px">{esc(c["label"])}</span>')


def status_pill(status: str) -> str:
    colors = {
        "active": ("#E5F3EA", "#1D6B3F", "Active"),
        "past_due": ("#FCEFD6", "#8A5300", "Past due"),
        "cancelled": ("#FBE7E4", "#A8261B", "Cancelled"),
    }
    bg, fg, label = colors[status]
    return f'<span class="pb-pill" style="background:{bg};color:{fg}">{label}</span>'


def kv_rows(rows: list[tuple[str, str]]) -> str:
    return "".join(f'<div class="pb-kv"><div>{esc(k)}</div><div>{esc(v)}</div></div>'
                   for k, v in rows)


def metric_card(label: str, value_html: str, sub: str, sub_color: str | None = None) -> str:
    style = f' style="color:{sub_color}"' if sub_color else ""
    return (f'<div class="pb-metric"><div class="pb-label">{esc(label)}</div>'
            f'<div class="pb-metric-value">{value_html}</div>'
            f'<div class="pb-metric-sub"{style}>{esc(sub)}</div></div>')


def info_box(text_html: str) -> str:
    return f'<div class="pb-info"><div style="font-weight:700">i</div><div>{text_html}</div></div>'


def trace_row(r: RuleResult) -> str:
    kind = r.status
    if r.status == "fail" and r.group in ("safety", "escalation"):
        kind = "flag"
    icon, bg, fg = STATUS_ICONS[kind]
    return (
        f'<div class="pb-rule"><div class="pb-icon" style="background:{bg};color:{fg}">{icon}</div>'
        f'<div><div class="pb-rule-name">{esc(r.name)}</div>'
        f'<div class="pb-rule-why">{esc(r.detail)}</div></div>'
        f'<div class="pb-rule-code">{esc(r.reason_code)}</div></div>'
    )


def banner(author: str, linkedin_url: str) -> None:
    html(
        f'<div class="pb-banner"><div><span class="pb-tag">Concept</span>'
        f'Unofficial concept · Synthetic data · Built by {esc(author)}</div>'
        f'<a href="{esc(linkedin_url)}" target="_blank">LinkedIn ↗</a></div>'
    )


def page_heading(title: str, subtitle: str) -> None:
    html(f'<div class="pb-title">{esc(title)}</div><div class="pb-subtitle">{esc(subtitle)}</div>')
