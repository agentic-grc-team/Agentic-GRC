"""Decision traces (E0-06 / AGRC-15).

Field names follow docs/design/trace-schema.md in feature/AGRC-15-trace-schema,
so moving from this JSONL file to the `decision_traces` table is a mapping, not
a redesign. Traces are append-only.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
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
    actor_type: Literal["agent", "assessed_org_representative", "aligo_consultant"] = "agent"
    model_name: str | None = None
    prompt_id: str | None = None  # an LLM prompt or a deterministic rule ("rule:...")
    prompt_version: str | None = None
    kb_version: str
    output: dict
    rationale: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    requires_human_review: bool = False
    # Not in the DB draft yet; useful for the 10 s NFR and the model benchmark.
    latency_ms: int | None = None
    fallback_used: bool = False


class TraceRecorder:
    def __init__(self, directory: Path | None = None):
        self.directory = directory
        self.records: list[DecisionTrace] = []
        if directory:
            directory.mkdir(parents=True, exist_ok=True)

    def record(self, trace: DecisionTrace) -> DecisionTrace:
        self.records.append(trace)
        if self.directory:
            path = self.directory / f"{trace.assessment_id}.jsonl"
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(trace.model_dump(), ensure_ascii=False) + "\n")
        return trace
