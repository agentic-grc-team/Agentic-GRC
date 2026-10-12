"""Versioned prompts. Bump the version whenever the wording changes:
the version is stored in every trace, so results can be compared across versions."""

from __future__ import annotations

from .schemas import Missing, Question

INTERPRET_ID, INTERPRET_VERSION = "interpret_answer", "0.2.0"
FOLLOW_UP_ID, FOLLOW_UP_VERSION = "generate_follow_up", "0.2.0"
CLARIFY_ID, CLARIFY_VERSION = "clarify_question", "0.2.0"

_ROLE = (
    "You are a cybersecurity consultant interviewing an organization to assess its security controls. "
    "You speak plain, friendly English, without standards jargon and without quoting any framework."
)


def _dialogue(turns: list[dict]) -> str:
    who = {"agent": "Consultant", "participant": "Participant"}
    return "\n".join(f"{who[t['speaker']]}: {t['content']}" for t in turns)


def interpret(question: Question, turns: list[dict]) -> tuple[str, str]:
    system = (
        f"{_ROLE}\n\nYour task: interpret EVERYTHING the participant has said about ONE question "
        "and return JSON matching the given schema. Do not invent information the participant did not say.\n\n"
        "Definitions:\n"
        "- intent: 'answer' if they answer; 'clarification_request' if they ask what the question means; "
        "'off_topic' if they talk about something else.\n"
        "- category: yes | no | partial | unsure | not_applicable.\n"
        "  'partial' = it exists but does not cover everything (some accounts, some systems, in progress).\n"
        "  'unsure' = they do not know or are not sure.\n"
        "- specificity: 'detailed' only if the answer includes the required detail; otherwise 'vague'.\n"
        "  For 'partial', detailed = they say what is missing. For 'not_applicable', detailed = they give a reason.\n"
        "- mentions_scope: true if they say which accounts, systems or people it applies to.\n"
        "- mentions_evidence: true if they mention something verifiable (policy, configuration, report, tool).\n"
        "- summary: one sentence in English paraphrasing the participant.\n"
        "- key_quote: a short literal fragment of the participant's LAST message.\n"
        "- confidence: 0 to 1, how sure you are of your interpretation."
    )
    user = (
        f"Question: {question.text}\n"
        f"What we need to learn: {question.intent}\n"
        f"Detail required to count as detailed: {question.detail_needed}\n\n"
        f"Conversation about this question:\n{_dialogue(turns)}"
    )
    return system, user


_MISSING_GOAL = {
    Missing.scope: "find out exactly which accounts or systems it applies to (all of them? cloud included?)",
    Missing.evidence: "ask for something verifiable that shows it (configuration, policy, screenshot, report)",
    Missing.gap: "find out which part is missing or not yet covered",
    Missing.justification: "ask why the control does not apply to their context",
    Missing.knowledge_owner: "ask who in the organization would know, or what they know for sure",
    Missing.redirect: "politely bring the conversation back to the original question",
}


def follow_up(question: Question, turns: list[dict], key_quote: str, missing: Missing) -> tuple[str, str]:
    system = (
        f"{_ROLE}\n\nWrite ONE short, friendly follow-up question that explicitly refers to what the "
        "participant just said. Do not repeat the original question word for word. "
        "Give no opinions or conclusions. Return JSON with the field 'question'."
    )
    user = (
        f"Original question: {question.text}\n"
        f"Goal of the follow-up: {_MISSING_GOAL[missing]}\n"
        f"What the participant said (to quote): \"{key_quote}\"\n\n"
        f"Conversation:\n{_dialogue(turns)}"
    )
    return system, user


def clarify(question: Question, participant_message: str) -> tuple[str, str]:
    system = (
        f"{_ROLE}\n\nThe participant did not understand the question. Explain it in at most 3 sentences, "
        "with an everyday example, and end by inviting them to answer. Do not answer for them. "
        "Return JSON with the field 'explanation'."
    )
    user = (
        f"Question: {question.text}\nWhat we need to learn: {question.intent}\n"
        f"Participant's message: {participant_message}"
    )
    return system, user


# Deterministic fallbacks used when the LLM is unavailable (degradation mechanism).
FALLBACK_FOLLOW_UPS = {
    Missing.scope: "You mentioned \"{quote}\". Which accounts or systems does it apply to exactly? Does it include cloud services?",
    Missing.evidence: "Understood: \"{quote}\". What could we look at to confirm it, for example a configuration or a policy?",
    Missing.gap: "You said \"{quote}\". Which part is not covered yet?",
    Missing.justification: "You mentioned \"{quote}\". Why does this control not apply to your organization?",
    Missing.knowledge_owner: "No problem. Who in the organization could confirm this?",
    Missing.redirect: "Let's go back to the question: {question}",
}
