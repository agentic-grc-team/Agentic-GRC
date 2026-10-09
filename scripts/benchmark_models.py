"""Compare Ollama models on the interpretation test set (E0-04 evidence).

    ollama pull qwen2.5:7b && ollama pull llama3.1:8b
    python scripts/benchmark_models.py qwen2.5:7b llama3.1:8b

Prints per-model accuracy (intent, category, specificity, resulting action),
JSON validity and latency p50/p95, and writes every prediction to
evals/results/<timestamp>.json so mistakes can be inspected.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_grc_agent import prompts  # noqa: E402
from agentic_grc_agent.config import Settings  # noqa: E402
from agentic_grc_agent.knowledge import load_kb  # noqa: E402
from agentic_grc_agent.llm import LLMError, OllamaLLM  # noqa: E402
from agentic_grc_agent.rules import decide_next_step  # noqa: E402
from agentic_grc_agent.schemas import AnswerInterpretation  # noqa: E402

FIELDS = ("intent", "category", "specificity", "action")


def to_turns(case: dict, question_text: str) -> list[dict]:
    turns = [{"speaker": "agent", "content": question_text}]
    for item in case["dialogue"]:
        (speaker, content), = item.items()
        turns.append({"speaker": speaker, "content": content})
    return turns


def percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


def run_model(model: str, cases: list[dict], kb, settings: Settings) -> dict:
    llm = OllamaLLM(model, settings.ollama_host, timeout_s=60, retries=0)  # generous timeout: we measure, not enforce
    hits = {f: [0, 0] for f in FIELDS}
    latencies, failures, rows = [], 0, []
    for case in cases:
        q = kb.get(case["question"])
        system, user = prompts.interpret(q, to_turns(case, q.text))
        try:
            interp, meta = llm.structured(prompt_id=prompts.INTERPRET_ID, prompt_version=prompts.INTERPRET_VERSION,
                                          system=system, user=user, schema=AnswerInterpretation)
        except LLMError as e:
            failures += 1
            rows.append({"case": case["id"], "error": str(e)})
            print(f"  ✗ {case['id']}: {e}")
            continue
        latencies.append(meta.latency_ms)
        step = decide_next_step(interp, follow_ups_used=0, max_follow_ups=settings.max_follow_ups)
        got = {
            "intent": interp.intent.value,
            "category": interp.category.value,
            "specificity": interp.specificity.value,
            "action": step.action.value,
        }
        wrong = []
        for field, expected in case["expected"].items():
            hits[field][1] += 1
            if got[field] == str(expected):
                hits[field][0] += 1
            else:
                wrong.append(f"{field}: expected {expected}, got {got[field]}")
        mark = "✓" if not wrong else "✗"
        print(f"  {mark} {case['id']} ({meta.latency_ms} ms) {'; '.join(wrong)}")
        rows.append({"case": case["id"], "got": got, "expected": case["expected"], "latency_ms": meta.latency_ms,
                     "interpretation": interp.model_dump(mode="json")})
    return {
        "model": model,
        "accuracy": {f: (h[0] / h[1] if h[1] else None) for f, h in hits.items()},
        "invalid_or_failed": failures,
        "latency_ms": {
            "p50": int(statistics.median(latencies)) if latencies else 0,
            "p95": percentile(latencies, 0.95),
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+")
    parser.add_argument("--cases", default=str(ROOT / "evals" / "interpret_cases.yaml"))
    args = parser.parse_args()

    settings = Settings()
    kb = load_kb(settings.kb_path)
    cases = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))["cases"]

    summaries = []
    for model in args.models:
        print(f"\n== {model} ==")
        summaries.append(run_model(model, cases, kb, settings))

    print(f"\n{'model':<20}" + "".join(f"{f:>13}" for f in FIELDS) + f"{'failed':>8}{'p50 ms':>9}{'p95 ms':>9}")
    for s in summaries:
        acc = "".join(f"{(s['accuracy'][f] or 0):>13.0%}" for f in FIELDS)
        print(f"{s['model']:<20}{acc}{s['invalid_or_failed']:>8}{s['latency_ms']['p50']:>9}{s['latency_ms']['p95']:>9}")
    print("\nNote: a real turn can add a second call (phrasing the follow-up).")

    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps({"prompt_version": prompts.INTERPRET_VERSION, "results": summaries},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Details: {out}")


if __name__ == "__main__":
    main()
