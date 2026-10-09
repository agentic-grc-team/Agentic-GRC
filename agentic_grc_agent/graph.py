"""LangGraph wiring of the interview.

    START → ask_question → wait_for_answer → interpret ─┬─ clarify ───┐
                 ▲                                      ├─ follow_up ─┤→ wait_for_answer
                 └──────── (next question) ── close_control ←─ close ─┘
                                                   └── (done) → END

`wait_for_answer` pauses the graph with `interrupt()`. The checkpointer saves
the state, so the interview can be resumed later with the same thread_id
(HU-09). Use a Postgres checkpointer in the backend; MemorySaver is for the CLI.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .nodes import Deps, InterviewNodes, InterviewState, initial_state  # noqa: F401  (re-exported)


def build_graph(deps: Deps, checkpointer=None):
    n = InterviewNodes(deps)

    def wait_for_answer(state: InterviewState) -> dict:
        # On resume this node runs again from the top and interrupt() returns the answer,
        # so nothing with side effects may happen before it.
        answer = interrupt({"message": state["pending_message"]})
        return n.record_answer(state, str(answer))

    g = StateGraph(InterviewState)
    g.add_node("ask_question", n.ask_question)
    g.add_node("wait_for_answer", wait_for_answer)
    g.add_node("interpret", n.interpret)
    g.add_node("clarify", n.clarify)
    g.add_node("follow_up", n.follow_up)
    g.add_node("close_control", n.close_control)

    g.add_edge(START, "ask_question")
    g.add_edge("ask_question", "wait_for_answer")
    g.add_edge("wait_for_answer", "interpret")
    g.add_conditional_edges(
        "interpret", n.route_after_interpret,
        {"clarify": "clarify", "follow_up": "follow_up", "close": "close_control"},
    )
    g.add_edge("clarify", "wait_for_answer")
    g.add_edge("follow_up", "wait_for_answer")
    g.add_conditional_edges("close_control", n.route_after_close, {"next": "ask_question", "done": END})

    return g.compile(checkpointer=checkpointer)
