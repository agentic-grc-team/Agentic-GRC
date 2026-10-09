import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_grc_agent.knowledge import load_kb  # noqa: E402
from agentic_grc_agent.nodes import InterviewNodes  # noqa: E402


@pytest.fixture
def kb():
    return load_kb(ROOT / "agentic_grc_agent" / "data" / "kb_demo.yaml")


def apply(state: dict, update: dict) -> dict:
    """Merge a node update the way LangGraph's reducers would."""
    new = dict(state)
    for k, v in update.items():
        if k == "turns":
            new[k] = state.get(k, []) + v
        elif k == "results":
            new[k] = {**state.get(k, {}), **v}
        else:
            new[k] = v
    return new


def run_scripted(nodes: InterviewNodes, state: dict, answers: list[str]) -> dict:
    """Drive the nodes in the same order as graph.py, feeding scripted answers."""
    state = apply(state, nodes.ask_question(state))
    for answer in answers:
        state = apply(state, nodes.record_answer(state, answer))
        state = apply(state, nodes.interpret(state))
        route = nodes.route_after_interpret(state)
        if route == "clarify":
            state = apply(state, nodes.clarify(state))
        elif route == "follow_up":
            state = apply(state, nodes.follow_up(state))
        else:
            state = apply(state, nodes.close_control(state))
            if nodes.route_after_close(state) == "done":
                break
            state = apply(state, nodes.ask_question(state))
    return state
