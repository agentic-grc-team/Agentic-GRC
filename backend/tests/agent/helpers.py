"""Helpers for the agent tests: run the interview nodes without LangGraph."""

from pathlib import Path

from app.agent.nodes import InterviewNodes

BACKEND_DIR = Path(__file__).resolve().parents[2]
KB_PATH = BACKEND_DIR / "app" / "agent" / "data" / "kb_demo.yaml"


def apply(state: dict, update: dict) -> dict:
    """Merge a node update the way LangGraph's reducers would."""
    new = dict(state)
    for k, v in update.items():
        if k in ("turns", "traces"):  # append-only, like operator.add in InterviewState
            new[k] = state.get(k, []) + v
        elif k == "results":
            new[k] = {**state.get(k, {}), **v}
        else:
            new[k] = v
    return new


def run_scripted(nodes: InterviewNodes, state: dict, answers: list[str]) -> dict:
    """Drive the nodes in the same order as graph.py, feeding scripted answers."""
    return run_scripted_more(nodes, apply(state, nodes.ask_question(state)), answers)


def run_scripted_more(nodes: InterviewNodes, state: dict, answers: list[str]) -> dict:
    """Continue an interview that is waiting for an answer."""
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
