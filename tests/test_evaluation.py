"""Evaluation harness tests — fake provider, no API calls."""

import json
import typing
from collections import Counter

import pytest

from triage.config import Category
from triage.evaluation import (
    confusion_counts,
    load_test_cases,
    per_category_accuracy,
    run_eval,
    score_run,
    summarize,
)
from triage.llm import LLMError
from triage.rules_engine import evaluate


@pytest.fixture(scope="module")
def cases():
    return load_test_cases()


# --- The test set itself ----------------------------------------------------


def test_thirty_unique_cases(cases):
    assert len(cases) == 30
    assert len({c.id for c in cases}) == 30


def test_every_category_has_at_least_three_cases(cases):
    counts = Counter(c.expected_category for c in cases)
    for category in typing.get_args(Category):
        assert counts[category] >= 3, category


def test_tricky_cases_are_covered(cases):
    tags = {t for c in cases for t in c.tags}
    for required in ["sarcasm", "multiple_issues", "non_english", "boundary", "prompt_injection"]:
        assert required in tags


def test_labels_agree_with_the_rules(cases, store, rules):
    """A perfect reader + the rules must reach each labeled decision.

    This checks the labels, so the eval measures only the AI's reading."""
    for case in cases:
        decision = evaluate(case.gold_classification(), case.message,
                            store.get_context(case.member_id), rules)
        assert decision.decision == case.expected_decision, case.id


# --- Running ----------------------------------------------------------------


class GoldProvider:
    """Answers every case with its gold label, optionally overriding some."""

    name, model = "fake", "fake-model"

    def __init__(self, cases, overrides=None, error=None):
        self.by_message = {c.message: c for c in cases}
        self.overrides = overrides or {}
        self.error = error
        self.calls = 0

    def complete_json(self, system, user, schema):
        self.calls += 1
        if self.error:
            raise self.error
        message = user.split("<member_message>\n", 1)[1].split("\n</member_message>", 1)[0]
        case = self.by_message[message]
        clf = case.gold_classification().model_dump()
        clf.update(self.overrides.get(case.id, {}))
        return json.dumps(clf)


def test_perfect_reader_scores_100_percent(cases):
    sleeps = []
    run = run_eval(GoldProvider(cases), cases, batch_id="b", pace_seconds=8, sleep=sleeps.append)
    score = score_run(run, cases)
    assert score.category_accuracy == 1.0 and score.decision_accuracy == 1.0
    assert run.prompt_version and run.model == "fake-model" and run.run_date


def test_calls_are_paced(cases):
    sleeps = []
    run_eval(GoldProvider(cases), cases, batch_id="b", pace_seconds=8, sleep=sleeps.append)
    assert len(sleeps) == len(cases) - 1
    assert all(7.5 < s <= 8 for s in sleeps)


def test_wrong_category_lowers_both_scores(cases):
    provider = GoldProvider(cases, overrides={"TC21": {"category": "return_remorse",
                                                       "sub_category": "changed_mind"}})
    score = score_run(run_eval(provider, cases, batch_id="b", sleep=lambda s: None), cases)
    assert score.category_accuracy == pytest.approx(29 / 30)
    assert score.decision_accuracy == pytest.approx(29 / 30)
    miss = next(c for c in score.cases if c.id == "TC21")
    assert miss.predicted_category == "return_remorse"


def test_right_decision_despite_wrong_category_counts_separately(cases):
    # Sync labeled as a warranty request still gets troubleshooting first.
    provider = GoldProvider(cases, overrides={"TC01": {"category": "warranty_replacement"}})
    score = score_run(run_eval(provider, cases, batch_id="b", sleep=lambda s: None), cases)
    assert score.category_accuracy == pytest.approx(29 / 30)
    assert score.decision_accuracy == 1.0


def test_rejected_api_key_stops_the_run(cases):
    provider = GoldProvider(cases, error=LLMError("auth", "bad key"))
    with pytest.raises(RuntimeError, match="API key"):
        run_eval(provider, cases, batch_id="b", sleep=lambda s: None)
    assert provider.calls == 1


# --- Summary ----------------------------------------------------------------


def test_summary_reports_mean_range_and_provenance(cases):
    perfect = run_eval(GoldProvider(cases), cases, batch_id="b", sleep=lambda s: None)
    flawed = run_eval(GoldProvider(cases, overrides={
        "TC21": {"category": "other"}, "TC27": {"category": "troubleshooting"},
    }), cases, batch_id="b", sleep=lambda s: None)
    runs = [perfect, flawed]
    scores = [score_run(r, cases) for r in runs]
    summary = summarize(scores, runs)

    cat = summary["category_accuracy"]
    assert cat["max"] == 1.0 and cat["min"] == pytest.approx(28 / 30, abs=1e-4)
    assert cat["mean"] == pytest.approx((1 + 28 / 30) / 2, abs=1e-4)
    assert summary["models"] == ["fake-model"]
    assert summary["prompt_versions"] and summary["run_dates"]
    assert per_category_accuracy(scores)["billing_membership"] == pytest.approx(5 / 6)
    assert confusion_counts(scores)[("other", "troubleshooting")] == 1
