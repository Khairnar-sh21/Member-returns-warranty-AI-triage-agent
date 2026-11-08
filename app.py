"""PulseBand Member Returns & Warranty AI Triage Agent — Streamlit app.

Run locally:  streamlit run app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from triage.config import RulesConfigError, get_rules
from ui import how_tab, session, sidebar, triage_tab
from ui.components import banner
from ui.settings import AUTHOR, LINKEDIN_URL
from ui.styles import inject_css

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

st.set_page_config(
    page_title="PulseBand Triage Agent · Unofficial concept",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _safe(render, name: str) -> None:
    try:
        render()
    except Exception:
        log.exception("%s failed to render", name)
        st.error(f"Sorry, the {name} view hit an unexpected problem. Refresh the page to try again.")


def _coming_soon(title: str, text: str) -> None:
    st.markdown(f"### {title}")
    st.info(text)


def main() -> None:
    inject_css()
    try:
        get_rules()
    except RulesConfigError as exc:
        st.error(f"The policy file has a problem, so the app can't make decisions safely. {exc}")
        st.stop()

    session.init()
    _safe(sidebar.render, "sidebar")
    banner(AUTHOR, LINKEDIN_URL)

    triage, ops, evaluation, how = st.tabs(["Triage", "Ops dashboard", "Evaluation", "How it works"])
    with triage:
        _safe(triage_tab.render, "Triage")
    with ops:
        _coming_soon("Ops dashboard", "Coming in Phase 6: automation rate, escalation rate, "
                     "cases by category and region, average confidence, and RMAs by warehouse.")
    with evaluation:
        _coming_soon("Evaluation", "Coming in Phase 6: 30 labeled scenarios with accuracy, "
                     "per-category accuracy, decision accuracy, and a confusion matrix.")
    with how:
        _safe(how_tab.render, "How it works")


main()
