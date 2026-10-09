"""Data contracts for the interview agent.

Everything the LLM returns is validated against one of these models, so the
rest of the code never parses free text.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Knowledge base (provisional, loaded from YAML until E0-03 exists)
# ---------------------------------------------------------------------------


class ControlMapping(BaseModel):
    node_code: str  # NIST CSF 2.0 subcategory, e.g. PR.AA-03
    justification: str
    confidence: float = Field(ge=0, le=1)


class Question(BaseModel):
    code: str
    module: str
    text: str  # business language, never the text of the standard
    intent: str  # what we actually need to learn (shown to the LLM, not the user)
    detail_needed: str  # what makes an affirmative answer "detailed"
    clarification: str  # static fallback explanation
    evidence_examples: list[str] = []
    mappings: list[ControlMapping]


class KnowledgeBase(BaseModel):
    kb_version: str
    is_provisional: bool = True
    language_code: str = "en"
    questions: list[Question]

    def get(self, code: str) -> Question:
        for q in self.questions:
            if q.code == code:
                return q
        raise KeyError(code)


# ---------------------------------------------------------------------------
# What the LLM returns
# ---------------------------------------------------------------------------


class Intent(str, Enum):
    answer = "answer"
    clarification_request = "clarification_request"
    off_topic = "off_topic"


class AnswerCategory(str, Enum):
    yes = "yes"
    no = "no"
    partial = "partial"
    unsure = "unsure"
    not_applicable = "not_applicable"


class Specificity(str, Enum):
    detailed = "detailed"
    vague = "vague"


class AnswerInterpretation(BaseModel):
    """Interpretation of everything the participant said about ONE question."""

    intent: Intent
    category: AnswerCategory = AnswerCategory.unsure
    specificity: Specificity = Specificity.vague
    mentions_scope: bool = False
    mentions_evidence: bool = False
    summary: str = Field(description="One sentence paraphrasing the participant")
    key_quote: str = Field(
        default="",
        description="Short literal fragment of the participant's last message to reference in a follow-up",
    )
    rationale: str
    confidence: float = Field(ge=0, le=1)


class FollowUpQuestion(BaseModel):
    question: str


class Clarification(BaseModel):
    explanation: str


# ---------------------------------------------------------------------------
# Decisions made by deterministic code
# ---------------------------------------------------------------------------


class ControlStatus(str, Enum):
    implemented = "implemented"
    partially_implemented = "partially_implemented"
    not_implemented = "not_implemented"
    not_applicable = "not_applicable"
    not_assessed = "not_assessed"


class Action(str, Enum):
    clarify = "clarify"
    follow_up = "follow_up"
    close = "close"


class Missing(str, Enum):
    """What a follow-up has to obtain. Code decides WHAT to ask; the LLM decides HOW."""

    scope = "scope"
    evidence = "evidence"
    gap = "gap"
    justification = "justification"
    knowledge_owner = "knowledge_owner"
    redirect = "redirect"


class NextStep(BaseModel):
    action: Action
    missing: Missing | None = None
    status: ControlStatus | None = None
    reason: str
    requires_human_review: bool = False
    rule_id: str  # recorded in the trace as the rule applied


class ControlResult(BaseModel):
    question_code: str
    status: ControlStatus
    reason: str
    summary: str
    follow_ups_used: int
    requires_human_review: bool
    evidence_pending: bool
    supporting_turns: list[int]  # sequence numbers of the participant turns
