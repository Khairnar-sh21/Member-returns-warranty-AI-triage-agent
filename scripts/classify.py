"""Try the live classifier + rules engine from the terminal.

  python scripts/classify.py "my band stopped charging after 5 months" --member M0001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage.classifier import classify  # noqa: E402
from triage.data import get_store  # noqa: E402
from triage.llm import LLMError, get_provider  # noqa: E402
from triage.rules_engine import evaluate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message")
    parser.add_argument("--member", help="member_id, e.g. M0001")
    args = parser.parse_args()

    try:
        provider = get_provider()
    except LLMError as exc:
        print(f"Config error: {exc}")
        return 1
    if provider is None:
        print("No API key found. Add GEMINI_API_KEY to .env (see .env.example).")
        return 1

    result = classify(args.message, provider)
    print(f"\n{result.provider}/{result.model} · {result.status} · "
          f"{result.attempts} attempt(s) · {result.latency_ms} ms")
    if result.error:
        print(f"⚠ {result.error}\n  detail: {result.error_detail}")
    print(result.classification.model_dump_json(indent=2))

    decision = evaluate(result.classification, args.message, get_store().get_context(args.member))
    print(f"\nDecision: {decision.decision}  ·  "
          f"{'Automated' if decision.automated else 'Escalated to human'}  ·  "
          f"queue={decision.assigned_queue}  ·  priority={decision.priority}")
    for r in decision.trace:
        print(f"  [{r.status:4}] {r.name}: {r.detail}")
    print(f"Next action: {decision.next_action}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
