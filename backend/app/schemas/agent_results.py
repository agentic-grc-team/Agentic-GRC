"""What the interview agent decided for one question (AGRC-32).

This is the contract between the agent and the backend. The agent closes one
question at a time and writes its result into the `output` of the
`status_assessed` trace; `from_agent_output()` turns that output into this
model, and `save_agent_result()` stores it as `control_results` rows.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.expert_review import ControlStatus


class AgentControlResult(BaseModel):
    question_code: str = Field(min_length=1)
    control_ids: list[str] = Field(min_length=1)  # NIST CSF 2.0 codes, e.g. ["PR.AA-03"]
    status: ControlStatus
    explanation: str
    justification: str | None = None  # required for not_applicable
    not_assessed_reason: str | None = None  # required for not_assessed
    confidence: float = Field(ge=0, le=1)
    requires_human_review: bool
    evidence_pending: bool

    @classmethod
    def from_agent_output(cls, output: dict[str, Any]) -> "AgentControlResult":
        """Map the agent's result (the `output` of its status_assessed trace) to this contract.

        The agent gives a `summary` of what the participant said and the `reason` of
        the rule that closed the question. The explanation shows both; a not_applicable
        justification is the participant's own reason, and a not_assessed reason is the
        rule's reason.
        """
        status = output["status"]
        summary = (output.get("summary") or "").strip()
        reason = (output.get("reason") or "").strip()
        return cls(
            question_code=output["question_code"],
            control_ids=output["control_ids"],
            status=status,
            explanation=f"{summary} {reason}".strip(),
            justification=summary if status == "not_applicable" else None,
            not_assessed_reason=reason if status == "not_assessed" else None,
            confidence=output["confidence"],
            requires_human_review=output["requires_human_review"],
            evidence_pending=output["evidence_pending"],
        )

    @field_validator("explanation", "justification", "not_assessed_reason")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def check_required_text(self) -> "AgentControlResult":
        # The same rules as the control_results CHECK constraints, with a clearer error.
        if not self.explanation:
            raise ValueError("An agent result needs an explanation.")
        if self.status == "not_applicable" and not self.justification:
            raise ValueError("A not_applicable result needs a justification.")
        if self.status == "not_assessed" and not self.not_assessed_reason:
            raise ValueError("A not_assessed result needs a reason.")
        if len(set(self.control_ids)) != len(self.control_ids):
            raise ValueError("control_ids must not repeat a control.")
        return self
