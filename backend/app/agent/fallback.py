"""Keyword heuristic used only when the LLM is unavailable (degradation path, E0-04).

It is deliberately crude and always reports low confidence, so any control
closed on top of it is flagged for human review by the rules.
"""

from __future__ import annotations

import re

from .schemas import AnswerCategory, AnswerInterpretation, Intent, Specificity

# Order matters: the first pattern that matches wins.
_PATTERNS: list[tuple[AnswerCategory, str]] = [
    (AnswerCategory.unsure, r"\b(i )?(don'?t|do not) know\b|\bnot sure\b|\bno idea\b|\bunsure\b"),
    (AnswerCategory.not_applicable, r"\bnot applicable\b|\bdoesn'?t apply\b|\bdoes not apply\b|\bn/?a\b|\bwe don'?t use\b"),
    (AnswerCategory.partial, r"\bpartial|\bsome\b|\bonly (in|for|on)\b|\bin progress\b|\bnot all\b|\bsort of\b|\bmore or less\b|\bmost\b"),
    (AnswerCategory.no, r"^\s*no\b|\bnever\b|\bwe don'?t have\b|\bthere (is|are) no\b|\bnone\b"),
    (AnswerCategory.yes, r"^\s*(yes|yeah|yep)\b|\bof course\b|\bsure\b|\ball\b|\balways\b"),
]


def heuristic_interpret(last_message: str) -> AnswerInterpretation:
    text = last_message.lower()
    if text.strip().endswith("?") or re.search(r"\bwhat does .* mean\b|\bi don'?t understand\b|\bwhat do you mean\b", text):
        intent, category = Intent.clarification_request, AnswerCategory.unsure
    else:
        intent = Intent.answer
        category = next((c for c, rx in _PATTERNS if re.search(rx, text)), AnswerCategory.unsure)
    return AnswerInterpretation(
        intent=intent,
        category=category,
        specificity=Specificity.vague,  # the heuristic never claims detail
        summary=last_message[:200],
        key_quote=last_message[:80],
        rationale="Keyword interpretation: the language model was unavailable.",
        confidence=0.3,
    )
