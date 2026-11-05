import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage.config import get_rules  # noqa: E402
from triage.data import get_store  # noqa: E402
from triage.rules_engine import evaluate  # noqa: E402
from triage.schemas import LLMClassification  # noqa: E402


def make_clf(category, sub_category="general", *, sentiment="neutral", urgency="normal",
             confidence=0.9, tried=False) -> LLMClassification:
    """A hand-written classification: stands in for the AI so rules are tested alone."""
    return LLMClassification(
        category=category,
        sub_category=sub_category,
        sentiment=sentiment,
        urgency=urgency,
        member_already_troubleshot=tried,
        confidence=confidence,
        reasoning_summary="test fixture",
    )


@pytest.fixture(scope="session")
def rules():
    return get_rules()


@pytest.fixture(scope="session")
def store():
    return get_store()


@pytest.fixture
def triage(store, rules):
    """triage("M0001", "warranty_replacement", "charging", tried=True, message="...")"""

    def _run(member_id, category, sub_category="general", *, message="", rules_override=None,
             **clf_kwargs):
        clf = make_clf(category, sub_category, **clf_kwargs)
        return evaluate(clf, message, store.get_context(member_id), rules_override or rules)

    return _run
