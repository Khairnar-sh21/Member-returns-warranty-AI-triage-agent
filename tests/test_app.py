"""Smoke test: the whole Streamlit app renders and triages in demo mode."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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
