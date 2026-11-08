"""Classify the sample scenarios with the live AI and save them for demo mode.

  python scripts/build_demo_cache.py

Paced to stay under the Gemini free-tier rate limit. Refuses to save if any
classification fell back, so the public demo never replays a failure.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage.classifier import PROMPT_VERSION, classify  # noqa: E402
from triage.demo import CACHE_PATH, DemoCache, load_scenarios, message_key  # noqa: E402
from triage.llm import get_provider  # noqa: E402
from triage.pipeline import triage_with_classification  # noqa: E402

SECONDS_BETWEEN_CALLS = 7


def main() -> int:
    provider = get_provider()
    if provider is None:
        print("No API key found. Add GEMINI_API_KEY to .env first.")
        return 1

    items, failures = {}, []
    scenarios = load_scenarios()
    for i, s in enumerate(scenarios):
        if i:
            time.sleep(SECONDS_BETWEEN_CALLS)
        result = classify(s.message, provider)
        outcome = triage_with_classification(s.message, s.member_id, result, mode="demo")
        c = result.classification
        print(f"{s.id:16} {result.status:8} {c.category:22} {c.confidence:.2f}  "
              f"→ {outcome.decision.decision} ({outcome.case.outcome})")
        if result.status == "fallback":
            failures.append(f"{s.id}: {result.error_detail}")
        items[message_key(s.message)] = result

    if failures:
        print("\nNot saved. These scenarios failed:\n  " + "\n  ".join(failures))
        return 1

    cache = DemoCache(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        provider=provider.name,
        model=provider.model,
        prompt_version=PROMPT_VERSION,
        items=items,
    )
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(cache.model_dump_json(indent=2))
    print(f"\nSaved {len(items)} classifications to {CACHE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
