"""Demo mode: sample scenarios + cached AI classifications.

Only the AI step is cached. The rules engine, case, RMA, and reply are always
recomputed, so editing rules.yaml changes demo results too. Because the AI
never sees account data, a cached classification is valid for any member.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from pydantic import BaseModel

from triage.classifier import ClassificationResult
from triage.config import DATA_DIR

SCENARIOS_PATH = DATA_DIR / "sample_scenarios.json"
CACHE_PATH = DATA_DIR / "cache" / "demo_classifications.json"


class Scenario(BaseModel):
    id: str
    label: str
    member_id: str
    message: str


class DemoCache(BaseModel):
    generated_at: str
    provider: str
    model: str
    prompt_version: str
    items: dict[str, ClassificationResult]


def message_key(message: str) -> str:
    normalized = " ".join(message.split()).lower()
    return hashlib.sha1(normalized.encode()).hexdigest()[:16]


@lru_cache(maxsize=1)
def load_scenarios() -> list[Scenario]:
    return [Scenario(**s) for s in json.loads(SCENARIOS_PATH.read_text())]


@lru_cache(maxsize=1)
def load_cache() -> DemoCache | None:
    if not CACHE_PATH.exists():
        return None
    return DemoCache.model_validate_json(CACHE_PATH.read_text())


def cached_classification(message: str) -> ClassificationResult | None:
    cache = load_cache()
    if cache is None:
        return None
    return cache.items.get(message_key(message))
