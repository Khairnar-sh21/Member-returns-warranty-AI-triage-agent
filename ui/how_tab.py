"""How it works: the flow, the AI's boundaries, and the live policy table."""

from __future__ import annotations

from collections import defaultdict

from triage.config import get_rules
from ui.components import esc, html, page_heading

FLOW = [
    ("01", "Member message", "Input", "Plain-English description, plus the member's account record "
     "(which only the rules see).", "“stopped charging after 5 months”", "plain"),
    ("02", "AI classification", "AI · probabilistic", "Returns category, sentiment, urgency, "
     "extracted facts and a confidence score as validated JSON.", "warranty_replacement · 0.95", "ai"),
    ("03", "Rules engine", "Rules · deterministic", "Applies the versioned policy in rules.yaml to "
     "the facts and the account. Same input, same decision, every time.", "WARRANTY_ACTIVE → approve",
     "rules"),
    ("04", "Case + RMA + Reply", "Output", "Writes the CRM case, creates an RMA only when approved, "
     "and fills the reply template from the rules' facts.", "CS-… ↔ RMA-…", "plain"),
    ("05", "Ops dashboard", "Monitoring", "Tracks automation, escalations and confidence so ops can "
     "tune thresholds.", "automation · escalation rates", "plain"),
]

STYLES = {
    "plain": ("#F7F8F9", "1px solid #E2E6E9", "#ECEFF1", "#3E4850"),
    "ai": ("#F2F8F8", "1px solid #9CC7C5", "#E6F2F1", "#0F6B6B"),
    "rules": ("#fff", "1.5px solid #0F6B6B", "#1B2228", "#fff"),
}

WHY = [
    ("Lower handling cost", "Automation rate",
     "Two-thirds of these scenarios resolve with no agent. Ops can raise or lower that by editing "
     "thresholds in rules.yaml, not by retraining a model."),
    ("Better member experience", "Fast, consistent answers",
     "Same facts, same decision, every time — including the last day of a return window and the "
     "day after. Members are not waiting on a queue for a policy lookup."),
    ("Clean data", "CRM case and ERP RMA always match",
     "The case and the return order share an ID and are created together. A retry cannot mint a "
     "duplicate replacement, and the two systems cannot drift."),
]


def _flow_html() -> str:
    parts = []
    for i, (n, title, tag, desc, example, kind) in enumerate(FLOW):
        bg, border, tag_bg, tag_fg = STYLES[kind]
        parts.append(
            f'<div class="pb-flow-step" style="background:{bg};border:{border}">'
            f'<div class="pb-mono pb-faint" style="font-size:13px">{n}</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.25">{esc(title)}</div>'
            f'<div><span class="pb-pill" style="font-size:12px;background:{tag_bg};color:{tag_fg}">'
            f'{esc(tag)}</span></div>'
            f'<div style="font-size:14px;line-height:1.5;color:#3E4850;flex:1">{esc(desc)}</div>'
            '<div class="pb-mono" style="font-size:12px;padding:8px 10px;background:#fff;'
            f'border:1px solid #E2E6E9;border-radius:6px;color:#3E4850">{esc(example)}</div></div>'
        )
        if i < len(FLOW) - 1:
            parts.append('<div class="pb-flow-arrow" aria-hidden="true">→</div>')
    return f'<div class="pb-flow">{"".join(parts)}</div>'


def _why_html() -> str:
    cards = "".join(
        f'<div class="pb-card pb-why-card"><div class="pb-label">{esc(metric)}</div>'
        f'<div class="pb-h-sm" style="margin:4px 0 8px">{esc(title)}</div>'
        f'<div style="font-size:14px;line-height:1.5;color:#3E4850">{esc(body)}</div></div>'
        for title, metric, body in WHY
    )
    return (
        '<div style="margin-top:28px"><div class="pb-h" style="margin-bottom:12px">Why it matters</div>'
        f'<div class="pb-why">{cards}</div></div>'
    )


def warranty_period_label(rules=None) -> str:
    """'Within 12 months of delivery; 24 months (EU and UK)'."""
    rules = rules or get_rules()
    w = rules.warranty
    grouped: dict[int, list[str]] = defaultdict(list)
    for region, months in w.months_by_region.items():
        grouped[months].append(region)
    extras = []
    for months, regions in grouped.items():
        if months == w.default_months:
            continue
        names = " and ".join(regions) if len(regions) <= 2 else ", ".join(regions)
        extras.append(f"{months} months ({names})")
    suffix = f"; {'; '.join(extras)}" if extras else ""
    return f"Within {w.default_months} months of delivery{suffix}"


def _policy_rows() -> list[tuple[str, str, str]]:
    r = get_rules()
    w, lim, e = r.warranty, r.warranty.replacement_limit, r.escalation
    return [
        ("Safety screen", f"AI says safety_concern, or one of {len(e.safety.keywords)} safety "
         "keywords appears", "Urgent → Trust & Safety; skip all eligibility rules"),
        ("Account lookup", "Member account linked", "Otherwise ask for account email or order number"),
        ("Troubleshooting first", f"{' / '.join(r.troubleshooting_first.sub_categories)} issue, "
         "member hasn't tried the standard steps", "Send guided troubleshooting before any RMA"),
        ("Warranty period", warranty_period_label(r),
         "Otherwise not eligible (offer upgrade options)"),
        ("Membership active", f"status == {w.required_membership_status}",
         "Past due → billing first; cancelled → not eligible"),
        ("Replacement limit", f"< {lim.max_replacements} warranty replacements in "
         f"{lim.rolling_window_months} months", "Otherwise manual review"),
        ("Return window", f"≤ {r.return_remorse.window_days} days since delivery",
         "Approve return + refund on receipt"),
        ("Lost package", f"> {r.shipping.lost_package_business_days} business days, no delivery scan",
         "Replacement, no return label"),
        ("Billing", "Category is billing / membership", "Billing queue; never an RMA"),
        ("Confidence gate", f"AI confidence ≥ {e.min_confidence:.2f}", "Otherwise human review"),
        ("Angry high-value member", f"Sentiment {' / '.join(e.angry_high_value.sentiments)} and "
         f"{' / '.join(e.angry_high_value.plans)} plan", "Escalate to an agent"),
        ("Possible fraud", f"≥ {e.possible_fraud.min_prior_cases} prior cases in "
         f"{e.possible_fraud.window_days} days", "Escalate to an agent"),
    ]


def _list_html(items: list[str], kind: str) -> str:
    icon = "✓" if kind == "allow" else "✕"
    return "".join(
        f'<div class="pb-bound"><span class="pb-bound-icon pb-bound-{kind}">{icon}</span>'
        f'<div>{esc(item)}</div></div>'
        for item in items
    )


def render() -> None:
    rules = get_rules()
    page_heading("How it works", "One request, five steps. The AI never decides an outcome — "
                 "it only produces structured facts for the rules.")
    html(f'<div style="margin-top:24px">{_flow_html()}</div>')
    html('<div class="pb-principle">AI for understanding, rules for decisions.</div>')
    html(_why_html())

    allowed = ["Classify category, sentiment and urgency",
               "Extract facts: issue, timing, steps already tried",
               "Report its own confidence (0–1)"]
    never = ["Approve a replacement, refund or return",
             "See account data or interpret warranty and return policy",
             "Create an RMA or change an order",
             "Write the member reply (templates are filled from the rules' facts)"]
    html(
        '<div class="pb-split" style="margin-top:24px">'
        '<div class="pb-card"><div class="pb-h-sm" style="margin-bottom:10px">The AI is allowed to</div>'
        + _list_html(allowed, "allow")
        + '</div><div class="pb-card"><div class="pb-h-sm" style="margin-bottom:10px">'
          'The AI is never allowed to</div>'
        + _list_html(never, "deny")
        + '</div></div>'
    )

    rows = "".join(
        f'<div class="pb-tr pb-policy-row">'
        f'<div class="pb-policy-rule">{esc(name)}</div>'
        f'<div class="pb-policy-if" data-label="If">{esc(cond)}</div>'
        f'<div class="pb-policy-then" data-label="Then">{esc(effect)}</div></div>'
        for name, cond, effect in _policy_rows()
    )
    html(
        '<div class="pb-policy-head">'
        f'<div class="pb-h">Policy rules · {esc(rules.policy.version)}</div>'
        '<div class="pb-muted" style="font-size:13px">Read live from rules.yaml · evaluated in order '
        '· safety overrides all</div></div>'
        '<div class="pb-table"><div class="pb-tr pb-th pb-policy-row"><div>Rule</div>'
        f'<div>Condition</div><div>Effect</div></div>{rows}</div>'
    )
