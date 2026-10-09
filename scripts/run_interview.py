"""Run the interview in the terminal against a local Ollama model.

    python scripts/run_interview.py                 # all demo questions
    python scripts/run_interview.py --only IAM-01   # just the MFA control
    AGRC_LLM_MODEL=llama3.1:8b python scripts/run_interview.py

Type /quit to stop. Traces are written to traces/<assessment_id>.jsonl.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agentic_grc_agent.config import Settings  # noqa: E402
from agentic_grc_agent.graph import build_graph, initial_state  # noqa: E402
from agentic_grc_agent.knowledge import load_kb  # noqa: E402
from agentic_grc_agent.llm import OllamaLLM  # noqa: E402
from agentic_grc_agent.nodes import Deps  # noqa: E402
from agentic_grc_agent.trace import TraceRecorder  # noqa: E402


def pending_interrupt(graph, config):
    snapshot = graph.get_state(config)
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="question codes to ask")
    args = parser.parse_args()

    settings = Settings()
    kb = load_kb(settings.kb_path)
    codes = args.only or [q.code for q in kb.questions]
    tracer = TraceRecorder(settings.trace_dir)
    llm = OllamaLLM(settings.llm_model, settings.ollama_host, settings.llm_timeout_s, settings.llm_retries)
    graph = build_graph(Deps(llm=llm, kb=kb, tracer=tracer, max_follow_ups=settings.max_follow_ups),
                        checkpointer=MemorySaver())

    assessment_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": assessment_id}}
    print(f"Model: {settings.llm_model} · KB {kb.kb_version} · assessment {assessment_id[:8]}\n")

    graph.invoke(initial_state("demo-org", assessment_id, codes), config)
    while (pending := pending_interrupt(graph, config)) is not None:
        print(f"\n🤖 {pending['message']}")
        answer = ""
        while not answer:
            answer = input("👤 ").strip()
        if answer == "/quit":
            break
        start = time.perf_counter()
        graph.invoke(Command(resume=answer), config)
        print(f"   ({time.perf_counter() - start:.1f} s)")

    results = graph.get_state(config).values.get("results", {})
    print("\n=== Result ===")
    for code, r in results.items():
        flag = " ⚠ needs human review" if r["requires_human_review"] else ""
        print(f"{code}: {r['status']} — {r['reason']}{flag}")
    print(f"\nTraces: {settings.trace_dir / (assessment_id + '.jsonl')}")


if __name__ == "__main__":
    main()
