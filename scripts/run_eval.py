"""Run the 30-case evaluation against the live model, paced for the free tier.

  python scripts/run_eval.py              # 3 runs, 8 s between calls (~12 min)
  python scripts/run_eval.py --runs 1
  python scripts/run_eval.py --rescore    # no API calls: re-score the latest batch

Each run is saved to data/eval/runs/ as soon as it finishes; the summary
(mean and range across the batch) goes to data/eval/summary.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage.evaluation import (  # noqa: E402
    DEFAULT_PACE_SECONDS,
    SUMMARY_PATH,
    latest_batch,
    load_runs,
    load_test_cases,
    run_eval,
    save_run,
    score_run,
    summarize,
)
from triage.llm import get_provider  # noqa: E402


def pct(x: float) -> str:
    return f"{x:.1%}"


def report(cases) -> int:
    runs = latest_batch(load_runs())
    if not runs:
        print("No saved runs yet.")
        return 1
    scores = [score_run(r, cases) for r in runs]
    summary = summarize(scores, runs)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    print(f"\nModel {', '.join(summary['models'])} · prompt {', '.join(summary['prompt_versions'])} · "
          f"policy {', '.join(summary['policy_versions'])}")
    for s in scores:
        print(f"  {s.run_id}: category {pct(s.category_accuracy)} · decision "
              f"{pct(s.decision_accuracy)} · fallbacks {s.fallbacks}")
    for key in ("category_accuracy", "decision_accuracy"):
        st = summary[key]
        print(f"{key.replace('_', ' ').capitalize():18} mean {pct(st['mean'])} "
              f"(range {pct(st['min'])}–{pct(st['max'])})")
    misses = sorted({(c.id, c.expected_decision, c.predicted_decision)
                     for s in scores for c in s.cases if not c.decision_correct})
    if misses:
        print("Decision misses (any run):")
        for cid, exp, got in misses:
            print(f"  {cid}: expected {exp}, got {got}")
    print(f"Saved {SUMMARY_PATH.relative_to(SUMMARY_PATH.parents[2])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--pace", type=float, default=DEFAULT_PACE_SECONDS,
                        help="seconds between API calls")
    parser.add_argument("--rescore", action="store_true")
    args = parser.parse_args()

    cases = load_test_cases()
    if args.rescore:
        return report(cases)

    provider = get_provider()
    if provider is None:
        print("No API key found. Add GEMINI_API_KEY to .env (see .env.example).")
        return 1

    batch_id = datetime.now(timezone.utc).strftime("batch_%Y%m%dT%H%M%SZ")
    eta = args.runs * len(cases) * args.pace / 60
    print(f"{args.runs} run(s) × {len(cases)} cases on {provider.name}/{provider.model}, "
          f"{args.pace:.0f} s apart (~{eta:.0f} min)", flush=True)

    def progress(i, case, result):
        clf = result.classification
        mark = "✓" if clf.category == case.expected_category else "✗"
        print(f"  [{i:2}/{len(cases)}] {case.id} {mark} {clf.category:22} "
              f"conf {clf.confidence:.2f} · {result.status}", flush=True)

    for n in range(1, args.runs + 1):
        if n > 1:
            time.sleep(args.pace)
        print(f"\nRun {n}/{args.runs}", flush=True)
        run = run_eval(provider, cases, batch_id=batch_id, pace_seconds=args.pace,
                       on_progress=progress)
        path = save_run(run)
        print(f"Saved {path.name} ({run.duration_seconds:.0f} s)", flush=True)

    return report(cases)


if __name__ == "__main__":
    sys.exit(main())
