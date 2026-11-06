"""Run one message through the full live pipeline from the terminal.

  python scripts/classify.py "my band stopped charging after 5 months" --member M0001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage.llm import LLMError, get_provider  # noqa: E402
from triage.outputs import DECISION_LABELS  # noqa: E402
from triage.pipeline import run_triage  # noqa: E402


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

    result = run_triage(args.message, args.member, provider)
    c, d = result.classification, result.decision
    print(f"\n{c.provider}/{c.model} · {c.status} · {c.attempts} attempt(s) · {c.latency_ms} ms")
    if c.error:
        print(f"⚠ {c.error}\n  detail: {c.error_detail}")
    print(c.classification.model_dump_json(indent=2))

    print(f"\n{DECISION_LABELS[d.decision]}  ·  "
          f"{'Automated' if d.automated else 'Escalated to human'}  ·  "
          f"queue={d.assigned_queue}  ·  priority={d.priority}")
    for r in d.trace:
        print(f"  [{r.status:4}] {r.name}: {r.detail}")

    print("\n--- Case ---\n" + result.case.model_dump_json(indent=2))
    if result.rma:
        print("\n--- RMA ---\n" + result.rma.model_dump_json(indent=2))
    print(f"\n--- Reply ---\nSubject: {result.reply.subject}\n\n{result.reply.body}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
