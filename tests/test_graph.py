"""Runs the real LangGraph graph with a fake LLM: interrupt, resume and checkpointing."""

import pytest

langgraph = pytest.importorskip("langgraph")

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agentic_grc_agent.graph import build_graph, initial_state  # noqa: E402
from agentic_grc_agent.llm import FakeLLM  # noqa: E402
from agentic_grc_agent.nodes import Deps  # noqa: E402
from agentic_grc_agent.schemas import AnswerInterpretation, FollowUpQuestion  # noqa: E402
from agentic_grc_agent.trace import TraceRecorder  # noqa: E402


def pending(graph, config):
    for task in graph.get_state(config).tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def test_graph_interrupts_and_resumes(kb):
    answers = iter([
        AnswerInterpretation(intent="answer", category="yes", summary="s", rationale="r", confidence=0.9),
        AnswerInterpretation(intent="answer", category="yes", specificity="detailed", mentions_scope=True,
                             summary="s", rationale="r", confidence=0.9),
    ])
    llm = FakeLLM({
        "interpret_answer": lambda _u: next(answers),
        "generate_follow_up": lambda _u: FollowUpQuestion(question="Which accounts does it apply to?"),
    })
    graph = build_graph(Deps(llm=llm, kb=kb, tracer=TraceRecorder()), checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    graph.invoke(initial_state("org", "t1", ["IAM-01"]), config)
    assert pending(graph, config)["message"] == kb.get("IAM-01").text

    graph.invoke(Command(resume="Yes"), config)
    assert pending(graph, config)["message"] == "Which accounts does it apply to?"

    graph.invoke(Command(resume="All of them, with Authenticator"), config)
    assert pending(graph, config) is None
    assert graph.get_state(config).values["results"]["IAM-01"]["status"] == "implemented"
