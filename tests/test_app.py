"""Smoke test: the whole Streamlit app renders and triages in demo mode."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import pandas as pd

from triage.config import DATA_DIR
from triage.demo import cached_classification, load_scenarios
from triage.pipeline import triage_with_classification

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")  # force demo mode regardless of local .env
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def test_app_loads_in_demo_mode_without_errors(app):
    assert not app.exception
    assert app.session_state["mode"] == "demo"
    assert [t.label for t in app.tabs] == ["Triage", "Ops dashboard", "Evaluation", "How it works"]
    assert not app.error


def test_app_defaults_to_demo_even_when_an_api_key_is_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-tests")
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    assert at.session_state["mode"] == "demo"


@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s.id)
def test_results_view_renders_for_every_demo_scenario(monkeypatch, scenario):
    # AppTest can't click while st.pills is on screen, so start on the results view.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    result = triage_with_classification(scenario.message, scenario.member_id,
                                        cached_classification(scenario.message), mode="demo")
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["result"] = result
    at.session_state["history"] = [result]
    at.run()
    assert not at.exception and not at.error
    assert any(b.label == "New request" for b in at.button)


SAMPLE_OUTCOMES = {
    "wont_charge": "approve_warranty_replacement",
    "return_germany": "approve_return",
    "charged_twice": "route_to_billing",
    "package_missing": "approve_lost_package_replacement",
    "skin_irritation": "escalate_safety",
    "angry_repeat": "manual_review_replacement_limit",
    "return_day_31": "deny_return_window_closed",
    "clasp_past_due": "hold_resolve_billing_first",
    "uk_sync": "approve_warranty_replacement",
    "vague": "escalate_to_human",
}

SAMPLE_NOTE_PHRASES = {
    "wont_charge": "warranty replacement approved",
    "return_germany": "remorse return in window",
    "charged_twice": "billing queue",
    "package_missing": "lost-package replacement",
    "skin_irritation": "urgent human review",
    "angry_repeat": "manual review",
    "return_day_31": "return window just closed",
    "clasp_past_due": "resolve billing before rma",
    "uk_sync": "warranty replacement approved",
    "vague": "human review",
}


def test_sample_scenarios_match_persona_notes_and_cached_outcomes():
    notes = dict(pd.read_csv(DATA_DIR / "personas.csv").set_index("member_id").scenario_note)
    for scenario in load_scenarios():
        result = triage_with_classification(
            scenario.message, scenario.member_id,
            cached_classification(scenario.message), mode="demo",
        )
        assert result.decision.decision == SAMPLE_OUTCOMES[scenario.id], scenario.id
        assert SAMPLE_NOTE_PHRASES[scenario.id] in notes[scenario.member_id].lower(), scenario.id
        assert "troubleshooting first" not in notes["M0001"].lower()
