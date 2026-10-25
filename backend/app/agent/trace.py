"""Decision trace value objects for the graph proof of concept (E0-06 / AGRC-15).

Durable production traces are written by the backend append-only service. This
module has no file-backed trace path.
"""

from __future__ import annotations

from collections.abc import Callable
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

DecisionType = Literal[
    "answer_interpreted",
    "evidence_requested",
    "status_assessed",
    "contradiction_detected",
    "human_review",
]


class TraceSource(BaseModel):
    type: Literal["interview_turn", "document_span", "tenant_configuration", "prior_phase_evidence"]
    ref: str
    excerpt: str | None = None


class DecisionTrace(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    organization_id: str
    assessment_id: str
    decision_type: DecisionType
    control_ids: list[str]
    module: str | None = None
    sources: list[TraceSource]
    evidence_nature: Literal["intent", "implementation", "attestation"] | None = None
    actor_type: Literal["agent", "assessed_org_representative", "aligo_consultant"] = "agent"
    model_name: str | None = None
    prompt_id: str | None = None  # an LLM prompt or a deterministic rule ("rule:...")
    prompt_version: str | None = None
    kb_version: str
    output: dict
    rationale: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    requires_human_review: bool = False
    latency_ms: int | None = None
    fallback_used: bool = False


class TraceRecorder:
    """In-memory trace collector with an optional durable backend sink.

    JSONL output was a proof-of-concept transport. Production traces are written
    through the backend append-only decision_traces service instead.
    """

    def __init__(self, persist: Callable[[DecisionTrace], object] | None = None):
        self.persist = persist
        self.records: list[DecisionTrace] = []

    def record(self, trace: DecisionTrace) -> DecisionTrace:
        if self.persist is not None:
            self.persist(trace)
        self.records.append(trace)
        return trace
