"""Compare Ollama models on the interpretation test set (E0-04 evidence).

    ollama pull qwen2.5:7b && ollama pull llama3.1:8b
    python scripts/benchmark_models.py qwen2.5:7b llama3.1:8b

Prints per-model accuracy (intent, category, specificity, resulting action),
JSON validity and latency p50/p95 (per call and per turn), and writes every
prediction to evals/results/<timestamp>-<model>.json so mistakes can be inspected.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.agent import prompts  # noqa: E402
from app.agent.config import Settings  # noqa: E402
from app.agent.knowledge import load_kb  # noqa: E402
from app.agent.llm import LLMError, OllamaLLM  # noqa: E402
from app.agent.rules import decide_next_step  # noqa: E402
from app.agent.schemas import (  # noqa: E402
    Action,
    AnswerInterpretation,
    Clarification,
    FollowUpQuestion,
    Missing,
)

FIELDS = ("intent", "category", "specificity", "mentions_evidence", "action")


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


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def summarize_latencies(call_ms: list[int], turn_ms: list[int]) -> dict:
    call_p50 = percentile(call_ms, 0.5)
    call_p95 = percentile(call_ms, 0.95)
    turn_p50 = percentile(turn_ms, 0.5)
    turn_p95 = percentile(turn_ms, 0.95)
    turns_over = sum(1 for t in turn_ms if t > 10000)
    turns_over_pct = (turns_over / len(turn_ms)) if turn_ms else 0.0

    return {
        "call_p50": call_p50,
        "call_p95": call_p95,
        "turn_p50": turn_p50,
        "turn_p95": turn_p95,
        "turns_over_10s": turns_over,
        "turns_over_10s_pct": turns_over_pct,
        "call": {"p50": call_p50, "p95": call_p95},
        "turn": {"p50": turn_p50, "p95": turn_p95},
    }


def run_model(model: str, cases: list[dict], kb, settings: Settings, repeat: int = 1, timeout: float = 60.0) -> dict:
    llm = OllamaLLM(
        model,
        settings.ollama_host,
        timeout_s=timeout,
        retries=0,  # generous timeout: we measure, not enforce
        keep_alive=settings.llm_keep_alive,
        num_predict=settings.llm_num_predict,
    )
    cold_load_ms = llm.warm_up()
    hits = {f: [0, 0] for f in FIELDS}
    call_latencies: list[int] = []
    turn_latencies: list[int] = []
    failures = 0
    rows = []

    for rep in range(repeat):
        for case in cases:
            q = kb.get(case["question"])
            turns = to_turns(case, q.text)
            system, user = prompts.interpret(q, turns)
            # A failed call still costs its time before the fallback, so failures add their elapsed time to the turn.
            started = time.perf_counter()
            try:
                interp, meta = llm.structured(
                    prompt_id=prompts.INTERPRET_ID,
                    prompt_version=prompts.INTERPRET_VERSION,
                    system=system,
                    user=user,
                    schema=AnswerInterpretation,
                )
            except LLMError as e:
                failures += 1
                turn_latencies.append(_elapsed_ms(started))
                if rep == 0:
                    rows.append({"case": case["id"], "error": str(e)})
                    print(f"  ✗ {case['id']}: {e}")
                continue

            call_latencies.append(meta.latency_ms)
            turn_ms = meta.latency_ms

            step = decide_next_step(
                interp,
                follow_ups_used=0,
                max_follow_ups=settings.max_follow_ups,
                evidence_asked=case.get("evidence_asked", False),
            )

            # Per-turn latency:
            # - follow_up (non-evidence): call generate_follow_up
            # - clarify: call clarify
            # - evidence or close: turn latency is just interpret latency
            if step.action == Action.follow_up and step.missing is not Missing.evidence:
                quote = interp.key_quote or turns[-1]["content"][:80]
                missing = step.missing or Missing.redirect
                f_system, f_user = prompts.follow_up(q, turns, quote, missing)
                started = time.perf_counter()
                try:
                    _, f_meta = llm.structured(
                        prompt_id=prompts.FOLLOW_UP_ID,
                        prompt_version=prompts.FOLLOW_UP_VERSION,
                        system=f_system,
                        user=f_user,
                        schema=FollowUpQuestion,
                    )
                    call_latencies.append(f_meta.latency_ms)
                    turn_ms += f_meta.latency_ms
                except LLMError as e:
                    failures += 1
                    turn_ms += _elapsed_ms(started)
                    if rep == 0:
                        print(f"  ✗ {case['id']} (follow-up call failed): {e}")
            elif step.action == Action.clarify:
                if step.rule_id == "rule:low_confidence_clarify":
                    c_system, c_user = prompts.ambiguity_clarification(q, turns[-1]["content"], interp.summary)
                    c_schema = FollowUpQuestion
                else:
                    # Same call as the clarify node in app/agent/nodes.py.
                    c_system, c_user = prompts.clarify(q, turns[-1]["content"])
                    c_schema = Clarification
                started = time.perf_counter()
                try:
                    _, c_meta = llm.structured(
                        prompt_id=prompts.CLARIFY_ID,
                        prompt_version=prompts.CLARIFY_VERSION,
                        system=c_system,
                        user=c_user,
                        schema=c_schema,
                    )
                    call_latencies.append(c_meta.latency_ms)
                    turn_ms += c_meta.latency_ms
                except LLMError as e:
                    failures += 1
                    turn_ms += _elapsed_ms(started)
                    if rep == 0:
                        print(f"  ✗ {case['id']} (clarify call failed): {e}")

            turn_latencies.append(turn_ms)

            # Accuracy uses the first run only
            if rep == 0:
                got = {
                    "intent": interp.intent.value,
                    "category": interp.category.value,
                    "specificity": interp.specificity.value,
                    "mentions_evidence": str(interp.mentions_evidence).lower(),
                    "action": step.action.value,
                }
                wrong = []
                for field, expected in case["expected"].items():
                    hits[field][1] += 1
                    if got[field] == str(expected).lower():
                        hits[field][0] += 1
                    else:
                        wrong.append(f"{field}: expected {expected}, got {got[field]}")
                mark = "✓" if not wrong else "✗"
                print(f"  {mark} {case['id']} (interpret: {meta.latency_ms} ms, turn: {turn_ms} ms) {'; '.join(wrong)}")
                rows.append({
                    "case": case["id"],
                    "got": got,
                    "expected": case["expected"],
                    "latency_ms": meta.latency_ms,
                    "turn_latency_ms": turn_ms,
                    "interpretation": interp.model_dump(mode="json"),
                })

    stats = summarize_latencies(call_latencies, turn_latencies)
    return {
        "model": model,
        "accuracy": {f: (h[0] / h[1] if h[1] else None) for f, h in hits.items()},
        "invalid_or_failed": failures,
        "cold_load_ms": cold_load_ms,
        "call_p50": stats["call_p50"],
        "call_p95": stats["call_p95"],
        "turn_p50": stats["turn_p50"],
        "turn_p95": stats["turn_p95"],
        "turns_over_10s": stats["turns_over_10s"],
        "turns_over_10s_pct": stats["turns_over_10s_pct"],
        "latency_ms": {
            "p50": stats["call_p50"],
            "p95": stats["call_p95"],
            "call_p50": stats["call_p50"],
            "call_p95": stats["call_p95"],
            "turn_p50": stats["turn_p50"],
            "turn_p95": stats["turn_p95"],
            "turns_over_10s": stats["turns_over_10s"],
        },
        "stats": stats,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+")
    parser.add_argument("--cases", default=str(ROOT / "evals" / "interpret_cases.yaml"))
    parser.add_argument("--repeat", type=int, default=1, help="number of times to run all cases")
    parser.add_argument("--machine", default=platform.node(), help="label stored in the results file")
    parser.add_argument("--timeout", type=float, default=60.0, help="per-call timeout in seconds")
    args = parser.parse_args()

    settings = Settings()
    kb = load_kb(settings.kb_path)
    cases = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))["cases"]

    summaries = []
    for model in args.models:
        print(f"\n== {model} ==")
        summaries.append(run_model(model, cases, kb, settings, repeat=args.repeat, timeout=args.timeout))

    print(f"\n{'model':<18}" + "".join(f"{f:>16}" for f in FIELDS) + f"{'failed':>8}{'call p50/p95':>16}{'turn p50/p95':>16}{'>10s':>10}{'cold load':>12}")
    for s in summaries:
        acc = "".join(f"{(s['accuracy'][f] or 0):>16.0%}" for f in FIELDS)
        call_str = f"{s['call_p50']}/{s['call_p95']} ms"
        turn_str = f"{s['turn_p50']}/{s['turn_p95']} ms"
        over_str = f"{s['turns_over_10s']} ({s['turns_over_10s_pct']:.0%})"
        cold_str = f"{s['cold_load_ms']} ms" if s['cold_load_ms'] is not None else "N/A"
        print(f"{s['model']:<18}{acc}{s['invalid_or_failed']:>8}{call_str:>16}{turn_str:>16}{over_str:>10}{cold_str:>12}")
    print("\nNote: turn latency includes follow-up phrasing or clarification when triggered; evidence requests use a template.")

    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    for s in summaries:
        safe_model = s["model"].replace(":", "-")
        out = out_dir / f"{timestamp}-{safe_model}.json"
        out_data = {
            "model": s["model"],
            "prompt_version": prompts.INTERPRET_VERSION,
            "machine": args.machine,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "keep_alive": settings.llm_keep_alive,
            "num_predict": settings.llm_num_predict,
            "timeout": args.timeout,
            "cold_load_ms": s["cold_load_ms"],
            "accuracy": s["accuracy"],
            "invalid_or_failed": s["invalid_or_failed"],
            "call_p50": s["call_p50"],
            "call_p95": s["call_p95"],
            "turn_p50": s["turn_p50"],
            "turn_p95": s["turn_p95"],
            "turns_over_10s": s["turns_over_10s"],
            "turns_over_10s_pct": s["turns_over_10s_pct"],
            "rows": s["rows"],
        }
        out.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Details: {out}")

    print("\nMarkdown table row for docs/ollama-setup.md:")
    today = datetime.now().strftime("%Y-%m-%d")
    for s in summaries:
        call_str = f"{s['call_p50']} / {s['call_p95']} ms"
        turn_str = f"{s['turn_p50']} / {s['turn_p95']} ms"
        over_str = f"{s['turns_over_10s']} ({s['turns_over_10s_pct']:.0%})"
        cold_str = f"{s['cold_load_ms']} ms" if s['cold_load_ms'] is not None else "N/A"
        row = (
            f"| {today} | {args.machine} | {s['model']} | {prompts.INTERPRET_VERSION} | "
            f"{call_str} | {turn_str} | {over_str} | {cold_str} | |"  # last cell: "Evaluation / Notes", filled by hand
        )
        print(row)


if __name__ == "__main__":
    main()
