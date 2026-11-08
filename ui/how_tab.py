"""How it works: the flow, the AI's boundaries, and the live policy table."""

from __future__ import annotations

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


def _flow_html() -> str:
    parts = []
    for i, (n, title, tag, desc, example, kind) in enumerate(FLOW):
        bg, border, tag_bg, tag_fg = STYLES[kind]
        parts.append(
            f'<div style="flex:1;min-width:0;background:{bg};border:{border};border-radius:10px;'
            'padding:18px 18px 20px;display:flex;flex-direction:column;gap:10px">'
            f'<div class="pb-mono pb-faint" style="font-size:13px">{n}</div>'
            f'<div style="font-size:18px;font-weight:600;line-height:1.25">{esc(title)}</div>'
            f'<div><span class="pb-pill" style="font-size:12px;background:{tag_bg};color:{tag_fg}">'
            f'{esc(tag)}</span></div>'
            f'<div style="font-size:14px;line-height:1.5;color:#3E4850;flex:1">{esc(desc)}</div>'
            '<div class="pb-mono" style="font-size:12px;padding:8px 10px;background:#fff;'
            f'border:1px solid #E2E6E9;border-radius:6px;color:#3E4850">{esc(example)}</div></div>'
        )
        if i < len(FLOW) - 1:
            parts.append('<div style="display:flex;align-items:center;color:#8A949C;'
                         'font-size:20px">→</div>')
    return f'<div style="display:flex;gap:8px;align-items:stretch">{"".join(parts)}</div>'


def _policy_rows() -> list[tuple[str, str, str]]:
    r = get_rules()
    w, lim, e = r.warranty, r.warranty.replacement_limit, r.escalation
    regional = ", ".join(f"{m} months ({reg})" for reg, m in w.months_by_region.items())
    return [
        ("Safety screen", f"AI says safety_concern, or one of {len(e.safety.keywords)} safety "
         "keywords appears", "Urgent → Trust & Safety; skip all eligibility rules"),
        ("Account lookup", "Member account linked", "Otherwise ask for account email or order number"),
        ("Troubleshooting first", f"{' / '.join(r.troubleshooting_first.sub_categories)} issue, "
         "member hasn't tried the standard steps", "Send guided troubleshooting before any RMA"),
        ("Warranty period", f"Within {w.default_months} months of delivery; {regional}",
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


def render() -> None:
    rules = get_rules()
    page_heading("How it works", "One request, five steps. The AI never decides an outcome — "
                 "it only produces structured facts for the rules.")
    html(f'<div style="margin-top:24px">{_flow_html()}</div>')
    html('<div style="text-align:center;font-size:30px;font-weight:600;padding:28px 0;'
         'color:#0A3F3F">AI for understanding, rules for decisions.</div>')

    allowed = ["Classify category, sentiment and urgency",
               "Extract facts: issue, timing, steps already tried",
               "Report its own confidence (0–1)"]
    never = ["Approve a replacement, refund or return",
             "See account data or interpret warranty and return policy",
             "Create an RMA or change an order",
             "Write the member reply (templates are filled from the rules' facts)"]
    html(
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">'
        '<div class="pb-card"><div class="pb-h-sm" style="margin-bottom:10px">The AI is allowed to</div>'
        + "".join(f'<div style="font-size:15px;line-height:1.5;margin:6px 0">✓ {esc(a)}</div>'
                  for a in allowed)
        + '</div><div class="pb-card"><div class="pb-h-sm" style="margin-bottom:10px">'
          'The AI is never allowed to</div>'
        + "".join(f'<div style="font-size:15px;line-height:1.5;margin:6px 0">✗ {esc(n)}</div>'
                  for n in never)
        + '</div></div>'
    )

    cols = "grid-template-columns:1.2fr 2.2fr 2fr"
    rows = "".join(
        f'<div class="pb-tr" style="{cols}"><div style="font-weight:500">{esc(name)}</div>'
        f'<div class="pb-mono" style="font-size:13px;color:#3E4850;padding-top:2px">{esc(cond)}</div>'
        f'<div style="color:#3E4850">{esc(effect)}</div></div>'
        for name, cond, effect in _policy_rows()
    )
    html(
        '<div style="display:flex;justify-content:space-between;align-items:baseline;margin:32px 0 12px">'
        f'<div class="pb-h">Policy rules · {esc(rules.policy.version)}</div>'
        '<div class="pb-muted" style="font-size:13px">Read live from rules.yaml · evaluated in order '
        '· safety overrides all</div></div>'
        f'<div class="pb-table"><div class="pb-tr pb-th" style="{cols}"><div>Rule</div>'
        f'<div>Condition</div><div>Effect</div></div>{rows}</div>'
    )
