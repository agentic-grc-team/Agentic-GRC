# Interview agent

First vertical slice of the Agentic GRC agent (E0-04 / E0-06, HU-05, HU-06, HU-08):
a conversational interview over 3 identity-and-access questions, in English,
with adaptive follow-ups, deterministic status rules and a decision trace for every step.
Runs entirely on a local Ollama model: no assessment data leaves the machine.

The agent lives in `backend/app/agent/` and the interview API runs it through
`app/services/interview_agent.py`. Commands below run from the `backend/` folder.

## Quick start

```bash
# 1. Ollama (https://ollama.com) running locally, plus the default model
ollama pull llama3.1:8b

# 2. Python 3.11+, from the backend/ folder
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Agent tests (no Ollama and no database needed: they use a fake LLM)
pytest tests/agent

# 4. Talk to the agent
python scripts/run_interview.py --only IAM-01   # type /quit to stop

# 5. Compare models on the labelled cases (accuracy + latency p50/p95)
ollama pull qwen2.5:7b
python scripts/benchmark_models.py qwen2.5:7b llama3.1:8b
```

Settings (env vars): `AGRC_LLM_MODEL` (default `llama3.1:8b`, see the decision record),
`AGRC_OLLAMA_HOST`, `AGRC_LLM_TIMEOUT_S` (default 8), `AGRC_LLM_RETRIES` (default 1, invalid output only),
`AGRC_MAX_FOLLOW_UPS` (default 3), `AGRC_KB_PATH`. The backend reads the same names through
`app/core/config.py`.

## Design: the LLM interprets, code decides

```
START → ask_question → wait_for_answer → interpret ─┬─ clarify ───┐
             ▲                                      ├─ follow_up ─┤→ wait_for_answer
             └──── (next question) ── close_control ←─ close ─────┘ → END
```

| Piece | File | Role |
|---|---|---|
| Interpretation | `prompts.py`, `llm.py` | LLM returns an `AnswerInterpretation` validated by Pydantic (Ollama `format` = JSON schema, temperature 0). It always sees the **whole dialogue on the current question**, so follow-ups accumulate. |
| Decision | `rules.py` | Pure Python. Picks clarify / follow-up / close, *what* is missing (scope, evidence, gap, justification…) and the status. Each branch has a `rule_id` stored in the trace. Same input → same decision. |
| Phrasing | `prompts.py` | The LLM only writes the wording of follow-ups and clarifications, citing what the participant said. |
| Degradation | `fallback.py`, `prompts.FALLBACK_FOLLOW_UPS` | If Ollama fails or times out: keyword interpretation (confidence 0.3) and template questions. The interview never stops, but a fallback interpretation never closes a control on its own (see the rules below). |
| Pause / resume | `graph.py` | `interrupt()` + a checkpointer keyed by `thread_id` (HU-09). The backend uses the Postgres checkpointer (`app/services/langgraph_checkpointer.py`, thread = interview session id); the CLI uses `MemorySaver`. |
| Traces | `trace.py` | Each decision is added to the graph state (`traces`) and the backend writes it to `decision_traces`. Fields follow the AGRC-15 trace schema (`decision_type`, `control_ids`, `sources`, `prompt_id`/`prompt_version`, `kb_version`, `output`, `rationale`, `confidence`, `requires_human_review`) plus `latency_ms` and `fallback_used`. |

Rules worth discussing with the team / Aligo (`rules.py`):

- A plain "no" closes as `not_implemented` without a follow-up (HU-06).
- A "yes" closes as `implemented` only with scope described, and only after one evidence request.
  Evidence is requested once per question, whatever the later answers look like, and even when the
  follow-up budget is used up; if the answer is still vague after that, the agent asks for the missing
  detail instead. Evidence stays pending: an answer is an attestation, not proof.
- The evidence request is a template built from the knowledge-base `evidence_examples`, not an LLM call,
  so that turn costs one model call instead of two.
- The rule does not use the model's `mentions_evidence` flag, which is only measured: `llama3.1:8b` got it
  right in 5 of 6 labelled cases with prompt v0.3.0, a sample too small to rely on.
- Every result is preliminary (`is_preliminary: true`) until an expert reviews it, and carries the confidence
  and the mapped control ids.
- After 3 follow-ups an unsupported "yes" closes as `not_assessed` + human review — never as compliant.
- `not_applicable` requires a justification (HU-08).
- An interpretation with confidence < 0.5 (always the case for the keyword fallback) never sets a status:
  the agent asks one focused clarification, and if the answer is still unclear it closes as
  `not_assessed` with human review.

## Knowledge base

`app/agent/data/kb_demo.yaml` is **provisional** (3 questions, draft CSF 2.0
mappings PR.AA-01/03/05). It mirrors the `questions` + `question_control_mappings`
tables of the DB schema, so swapping it for the real KB (E0-03) only changes the loader.

## Evaluation set

`evals/interpret_cases.yaml`: 20 labelled answers (vague yes, partial, unsure,
clarification, off-topic, multi-turn…). `tests/agent/test_rules.py` checks the labels are
consistent with the rules; `scripts/benchmark_models.py` measures each model against them.
Note: quote `"yes"` / `"no"` in YAML, otherwise they load as booleans.

Prompts, knowledge base and evaluation cases are in English (`language_code: en` in the KB).
To add another language, translate `kb_demo.yaml`, `prompts.py` and the eval cases together.

## Not in this slice (next steps)

Contradiction detection (HU-07), linking uploaded evidence documents to agent results (E3).
