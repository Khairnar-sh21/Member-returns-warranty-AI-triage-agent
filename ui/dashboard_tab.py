"""Ops dashboard: KPIs across this session's cases plus a pre-run batch."""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from triage.data import get_store
from triage.evaluation import latest_batch, load_runs, load_test_cases
from triage.outputs import DECISION_LABELS
from triage.pipeline import TriageResult, triage_with_classification
from ui.charts import hbar
from ui.components import CATEGORY_LABELS, QUEUE_LABELS, html, info_box, metric_card, page_heading
from ui.styles import OUTCOME_COLORS

REGION_ORDER = ["US", "CA", "UK", "EU", "AU", "No account"]
WAREHOUSE_ORDER = ["US", "EU", "APAC"]


@st.cache_data(show_spinner=False)
def _batch_records() -> list[dict]:
    """The 30 eval scenarios, replayed through the pipeline from saved AI outputs."""
    runs = latest_batch(load_runs())
    if not runs:
        return []
    run = runs[0]
    records = []
    for case in load_test_cases():
        result = triage_with_classification(case.message, case.member_id,
                                            run.classifications[case.id], mode="demo")
        records.append(_record(result, "Pre-run batch"))
    return records


def _record(r: TriageResult, source: str) -> dict:
    member = get_store().members.get(r.member_id) if r.member_id else None
    return {
        "Source": source,
        "Case": r.case.case_id,
        "Category": CATEGORY_LABELS[r.case.category],
        "Region": member.region if member else "No account",
        "Outcome": r.case.outcome,
        "Decision": DECISION_LABELS[r.case.decision],
        "Queue": QUEUE_LABELS.get(r.case.assigned_queue, r.case.assigned_queue),
        "Confidence": r.case.ai_confidence,
        "RMA warehouse": r.rma.warehouse if r.rma else None,
    }


def _ordered_counts(values, order) -> tuple[list[str], list[int]]:
    counts = Counter(values)
    labels = [k for k in order if counts.get(k)] + sorted(k for k in counts if k not in order)
    return labels, [counts[k] for k in labels]


def render() -> None:
    page_heading("Ops dashboard",
                 "How the agent is performing across every case triaged in this session, "
                 "plus a pre-run batch of 30 scenarios.")
    st.write("")

    session_records = [_record(r, "This session") for r in st.session_state.get("history", [])]
    batch = _batch_records()
    include_batch = st.toggle(f"Include pre-run batch ({len(batch)} scenarios)",
                              value=True, disabled=not batch)
    records = session_records + (batch if include_batch else [])

    if not records:
        html(info_box("No cases yet. Triage a request on the Triage tab and it will appear here."))
        return

    df = pd.DataFrame(records)
    n = len(df)
    automated = (df.Outcome == "automated").sum()
    escalated = (df.Outcome == "escalated").sum()
    review = (df.Outcome == "needs_review").sum()
    rmas = df["RMA warehouse"].notna().sum()

    cards = st.columns(5)
    cards[0].html(metric_card("Cases", str(n),
                              f"{len(session_records)} this session · "
                              f"{n - len(session_records)} batch"))
    cards[1].html(metric_card("Automation rate", f"{automated / n:.0%}",
                              f"{automated} resolved with no human review"))
    cards[2].html(metric_card("Escalation rate", f"{(escalated + review) / n:.0%}",
                              f"{escalated} escalated · {review} needs review"))
    cards[3].html(metric_card("Avg AI confidence", f"{df.Confidence.mean():.2f}",
                              f"{(df.Confidence < 0.7).sum()} below the 0.70 threshold"))
    cards[4].html(metric_card("RMAs created", str(rmas), "returns and replacements"))
    st.write("")

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Cases by category**")
        labels, values = _ordered_counts(df.Category, list(CATEGORY_LABELS.values()))
        st.plotly_chart(hbar(labels, values), config={"displayModeBar": False})

        st.markdown("**Outcome mix**")
        order = list(OUTCOME_COLORS)
        labels, values = _ordered_counts(df.Outcome, order)
        st.plotly_chart(
            hbar([OUTCOME_COLORS[k]["label"] for k in labels], values,
                 colors=[OUTCOME_COLORS[k]["fg"] for k in labels],
                 text=[f"{v} ({v / n:.0%})" for v in values], height=170),
            config={"displayModeBar": False},
        )
    with right:
        st.markdown("**Cases by region**")
        labels, values = _ordered_counts(df.Region, REGION_ORDER)
        st.plotly_chart(hbar(labels, values), config={"displayModeBar": False})

        st.markdown("**RMAs by warehouse**")
        if rmas:
            labels, values = _ordered_counts(df["RMA warehouse"].dropna(), WAREHOUSE_ORDER)
            st.plotly_chart(hbar(labels, values, height=170), config={"displayModeBar": False})
        else:
            st.caption("No RMAs created yet.")

    st.markdown("**Cases**")
    st.dataframe(
        df[["Source", "Case", "Category", "Region", "Decision", "Queue", "Confidence"]],
        hide_index=True,
        column_config={"Confidence": st.column_config.NumberColumn(format="%.2f")},
    )
