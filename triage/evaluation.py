"""Evaluation harness: 30 labeled scenarios, scored on category and decision.

Each run stores the AI's raw classification for every case, plus the model,
prompt version, policy version, and run date. Scores are always recomputed
from those stored classifications, so results are reproducible without new
API calls and can be re-scored after a rules change.

Category accuracy  = did the AI pick the labeled category?
Decision accuracy  = did the whole pipeline reach the labeled decision?
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Callable

from pydantic import BaseModel

from triage.classifier import PROMPT_VERSION, ClassificationResult, classify
from triage.config import DATA_DIR, Category, Rules, get_rules
from triage.data import DataStore, get_store
from triage.llm import LLMProvider
from triage.rules_engine import evaluate
from triage.schemas import DecisionCode, LLMClassification, Sentiment

TEST_CASES_PATH = DATA_DIR / "test_cases.json"
RUNS_DIR = DATA_DIR / "eval" / "runs"
SUMMARY_PATH = DATA_DIR / "eval" / "summary.json"

# Gemini free tier allows 10 requests/minute; 8 s between cases leaves headroom
# for the classifier's own retries.
DEFAULT_PACE_SECONDS = 8.0


class GoldLabel(BaseModel):
    sub_category: str
    sentiment: Sentiment
    member_already_troubleshot: bool


class TestCase(BaseModel):
    id: str
    member_id: str | None
    message: str
    expected_category: Category
    expected_decision: DecisionCode
    gold: GoldLabel
    tags: list[str] = []

    def gold_classification(self) -> LLMClassification:
        """What a perfect reader would output; used to check the labels themselves."""
        return LLMClassification(
            category=self.expected_category,
            sub_category=self.gold.sub_category,
            sentiment=self.gold.sentiment,
            urgency="normal",
            member_already_troubleshot=self.gold.member_already_troubleshot,
            confidence=1.0,
            reasoning_summary="gold label",
        )


class EvalRun(BaseModel):
    run_id: str
    batch_id: str
    run_date: str  # ISO 8601, UTC
    provider: str
    model: str
    prompt_version: str
    policy_version: str
    pace_seconds: float
    duration_seconds: float
    classifications: dict[str, ClassificationResult]  # case id → raw AI output


class CaseScore(BaseModel):
    id: str
    tags: list[str]
    expected_category: str
    predicted_category: str
    expected_decision: str
    predicted_decision: str
    category_correct: bool
    decision_correct: bool
    confidence: float
    status: str


class RunScore(BaseModel):
    run_id: str
    run_date: str
    model: str
    prompt_version: str
    n: int
    category_accuracy: float
    decision_accuracy: float
    fallbacks: int
    cases: list[CaseScore]


def load_test_cases(path: Path = TEST_CASES_PATH) -> list[TestCase]:
    return [TestCase(**c) for c in json.loads(path.read_text())]


# -----------------------------------------------------------------------------
# Running (live API calls)
# -----------------------------------------------------------------------------


def run_eval(
    provider: LLMProvider,
    cases: list[TestCase],
    *,
    batch_id: str,
    pace_seconds: float = DEFAULT_PACE_SECONDS,
    on_progress: Callable[[int, TestCase, ClassificationResult], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> EvalRun:
    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    t0 = time.monotonic()
    classifications: dict[str, ClassificationResult] = {}
    last_call = None

    for i, case in enumerate(cases, 1):
        if last_call is not None:
            wait = pace_seconds - (time.monotonic() - last_call)
            if wait > 0:
                sleep(wait)
        last_call = time.monotonic()
        result = classify(case.message, provider)
        classifications[case.id] = result
        if on_progress:
            on_progress(i, case, result)
        if result.error_kind == "auth":
            raise RuntimeError(f"Stopping: the API key was rejected ({result.error_detail}).")

    return EvalRun(
        run_id=started_at.strftime("run_%Y%m%dT%H%M%SZ"),
        batch_id=batch_id,
        run_date=started_at.isoformat(),
        provider=provider.name,
        model=provider.model,
        prompt_version=PROMPT_VERSION,
        policy_version=get_rules().policy.version,
        pace_seconds=pace_seconds,
        duration_seconds=round(time.monotonic() - t0, 1),
        classifications=classifications,
    )


def save_run(run: EvalRun, runs_dir: Path = RUNS_DIR) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run.run_id}.json"
    path.write_text(run.model_dump_json(indent=2))
    return path


def load_runs(runs_dir: Path = RUNS_DIR) -> list[EvalRun]:
    if not runs_dir.exists():
        return []
    return [EvalRun.model_validate_json(p.read_text()) for p in sorted(runs_dir.glob("run_*.json"))]


def latest_batch(runs: list[EvalRun]) -> list[EvalRun]:
    if not runs:
        return []
    batch = runs[-1].batch_id
    return [r for r in runs if r.batch_id == batch]


# -----------------------------------------------------------------------------
# Scoring (no API calls)
# -----------------------------------------------------------------------------


def score_run(
    run: EvalRun,
    cases: list[TestCase],
    *,
    store: DataStore | None = None,
    rules: Rules | None = None,
) -> RunScore:
    store = store or get_store()
    rules = rules or get_rules()
    scores = []
    for case in cases:
        result = run.classifications[case.id]
        clf = result.classification
        decision = evaluate(clf, case.message, store.get_context(case.member_id), rules)
        scores.append(CaseScore(
            id=case.id,
            tags=case.tags,
            expected_category=case.expected_category,
            predicted_category=clf.category,
            expected_decision=case.expected_decision,
            predicted_decision=decision.decision,
            category_correct=clf.category == case.expected_category,
            decision_correct=decision.decision == case.expected_decision,
            confidence=clf.confidence,
            status=result.status,
        ))
    n = len(scores)
    return RunScore(
        run_id=run.run_id,
        run_date=run.run_date,
        model=run.model,
        prompt_version=run.prompt_version,
        n=n,
        category_accuracy=sum(s.category_correct for s in scores) / n,
        decision_accuracy=sum(s.decision_correct for s in scores) / n,
        fallbacks=sum(s.status == "fallback" for s in scores),
        cases=scores,
    )


def per_category_accuracy(scores: list[RunScore]) -> dict[str, float]:
    """Category accuracy by expected category, pooled across runs."""
    hits, totals = defaultdict(int), defaultdict(int)
    for run in scores:
        for c in run.cases:
            totals[c.expected_category] += 1
            hits[c.expected_category] += c.category_correct
    return {cat: hits[cat] / totals[cat] for cat in totals}


def confusion_counts(scores: list[RunScore]) -> Counter:
    """(expected category, predicted category) → count, pooled across runs."""
    return Counter((c.expected_category, c.predicted_category) for run in scores for c in run.cases)


def summarize(scores: list[RunScore], runs: list[EvalRun]) -> dict:
    def stat(values: list[float]) -> dict:
        return {"mean": round(mean(values), 4), "min": round(min(values), 4),
                "max": round(max(values), 4), "runs": [round(v, 4) for v in values]}

    return {
        "n_runs": len(scores),
        "n_cases": scores[0].n,
        "provider": runs[0].provider,
        "models": sorted({r.model for r in runs}),
        "prompt_versions": sorted({r.prompt_version for r in runs}),
        "policy_versions": sorted({r.policy_version for r in runs}),
        "run_dates": [r.run_date for r in runs],
        "category_accuracy": stat([s.category_accuracy for s in scores]),
        "decision_accuracy": stat([s.decision_accuracy for s in scores]),
        "per_category_accuracy": {k: round(v, 4) for k, v in
                                  sorted(per_category_accuracy(scores).items())},
        "fallbacks": sum(s.fallbacks for s in scores),
    }
