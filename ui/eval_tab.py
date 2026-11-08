"""Evaluation tab: accuracy across repeated runs of the 30 labeled scenarios."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from triage.evaluation import (
    confusion_counts,
    latest_batch,
    load_runs,
    load_test_cases,
    per_category_accuracy,
    score_run,
    summarize,
)
from triage.outputs import DECISION_LABELS
from ui.charts import hbar, heatmap
from ui.components import CATEGORY_LABELS, esc, html, info_box, metric_card, page_heading
from ui.styles import TEAL


def _pct(x: float) -> str:
    return f"{x:.0%}" if round(x * 100, 1).is_integer() else f"{x:.1%}"


def _stat_text(stat: dict) -> tuple[str, str]:
    if stat["min"] == stat["max"]:
        return _pct(stat["mean"]), "identical across runs"
    return _pct(stat["mean"]), f"range {_pct(stat['min'])}–{_pct(stat['max'])} across runs"


def _date(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%b %d, %Y %H:%M UTC")


def _score():
    cases = load_test_cases()
    runs = latest_batch(load_runs())
    scores = [score_run(r, cases) for r in runs]
    return cases, runs, scores


def render() -> None:
    page_heading("Evaluation",
                 "30 labeled scenarios covering every category, policy boundary dates, "
                 "sarcasm, multiple issues in one message, non-English messages, and a "
                 "prompt-injection attempt.")
    st.write("")

    if st.button("Run all 30 scenarios", type="primary"):
        with st.spinner("Replaying saved AI outputs through the current rules…"):
            st.session_state.eval_scored = _score()
    st.caption("Replays the AI outputs saved from each live run through the current rules, "
               "so it's instant and free. New live runs (90 paced API calls) are made "
               "offline with scripts/run_eval.py.")

    if "eval_scored" not in st.session_state:
        st.session_state.eval_scored = _score()
    cases, runs, scores = st.session_state.eval_scored
    if not scores:
        html(info_box("No evaluation runs saved yet. Run <code>python scripts/run_eval.py</code> "
                      "with an API key to create them."))
        return

    summary = summarize(scores, runs)
    html(
        '<div class="pb-note" style="margin:6px 0 14px">'
        f'<b>Model</b> {esc(", ".join(summary["models"]))} · '
        f'<b>Prompt</b> {esc(", ".join(summary["prompt_versions"]))} · '
        f'<b>Policy</b> {esc(", ".join(summary["policy_versions"]))} · '
        f'<b>Runs</b> {esc(", ".join(_date(d) for d in summary["run_dates"]))}</div>'
    )

    cat_value, cat_sub = _stat_text(summary["category_accuracy"])
    dec_value, dec_sub = _stat_text(summary["decision_accuracy"])
    cards = st.columns(4)
    cards[0].html(metric_card("Category accuracy (mean)", cat_value, cat_sub))
    cards[1].html(metric_card("Decision accuracy (mean)", dec_value, dec_sub))
    cards[2].html(metric_card("Runs × scenarios", f"{len(scores)} × {summary['n_cases']}",
                              f"{len(scores) * summary['n_cases']} AI classifications"))
    cards[3].html(metric_card("AI fallbacks", str(summary["fallbacks"]),
                              "API errors or unreadable output"))
    st.write("")

    st.markdown("**Each run**")
    st.dataframe(pd.DataFrame([{
        "Run": _date(s.run_date),
        "Category accuracy": s.category_accuracy,
        "Decision accuracy": s.decision_accuracy,
        "Fallbacks": s.fallbacks,
    } for s in scores]), hide_index=True, column_config={
        "Category accuracy": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "Decision accuracy": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
    })

    left, right = st.columns([5, 6], gap="large")
    with left:
        st.markdown("**Category accuracy by category** (pooled across runs)")
        per_cat = per_category_accuracy(scores)
        labels = [c for c in CATEGORY_LABELS if c in per_cat]
        values = [per_cat[c] for c in labels]
        st.plotly_chart(
            hbar([CATEGORY_LABELS[c] for c in labels], values, text=[_pct(v) for v in values],
                 colors=[TEAL if v >= 0.9 else "#C98A1B" for v in values], height=300,
                 x_range=[0, 1.18]),
            config={"displayModeBar": False},
        )
    with right:
        st.markdown("**Confusion matrix** (expected vs. AI-predicted category, all runs)")
        counts = confusion_counts(scores)
        cats = list(CATEGORY_LABELS)
        z = [[counts.get((e, p), 0) for p in cats] for e in cats]
        names = [CATEGORY_LABELS[c] for c in cats]
        st.plotly_chart(heatmap(z, names, names), config={"displayModeBar": False})

    st.markdown("**Scenario results**")
    rows = []
    for i, case in enumerate(cases):
        per_run = [s.cases[i] for s in scores]
        rows.append({
            "ID": case.id,
            "Message": case.message,
            "Tags": ", ".join(t.replace("_", " ") for t in case.tags),
            "Expected category": CATEGORY_LABELS[case.expected_category],
            "Category ✓": f"{sum(c.category_correct for c in per_run)}/{len(per_run)}",
            "Expected decision": DECISION_LABELS[case.expected_decision],
            "Decision ✓": f"{sum(c.decision_correct for c in per_run)}/{len(per_run)}",
            "AI got (if wrong)": ", ".join(sorted({
                f"{CATEGORY_LABELS[c.predicted_category]} → {DECISION_LABELS[c.predicted_decision]}"
                for c in per_run if not c.decision_correct or not c.category_correct
            })),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={
        "Message": st.column_config.TextColumn(width="large"),
    })
