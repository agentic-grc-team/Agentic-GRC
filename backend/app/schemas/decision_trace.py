from dataclasses import dataclass


@dataclass
class DecisionTrace:
    decision_type: str
    actor_type: str
    sources: list
    rationale: str
    model_name: str | None = None
    prompt_version: str | None = None
    confidence: float | None = None