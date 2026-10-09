# E0-04 — Agent architecture, LLM selection and data policy

Status: proposed · Date: 2026-10-08 · Backlog item: E0-04 · Code: `agent/`

## Context and status

Proposed decision: the agent runs as a LangGraph state machine over a local Ollama model, where the LLM interprets answers and deterministic code makes every assessment decision. Status is **proposed**, pending team review; the model is chosen, but its latency is still above the 10 s turn target (see LLM selection).

Backlog item E0-04 (Sprint 1, Must, 5 pts) asks for four things: the orchestration library, LLM and session-memory strategy; a written policy on what data may leave for external APIs; a cost estimate per complete assessment; and a degradation mechanism for when the LLM fails or exceeds the time limit.

The decisions are backed by a working proof of concept: a 3-question interview (identity and access, mapped to draft CSF 2.0 subcategories PR.AA-01, PR.AA-03, PR.AA-05) with adaptive follow-ups, traces and a model benchmark. The interview language is **English**.

## Decision summary

| Area | Decision | Why |
| --- | --- | --- |
| Orchestration | LangGraph (Python) | Explicit state machine fits a structured interview; built-in interrupt and checkpointing give pause/resume (HU-09) |
| LLM runtime | Ollama, self-hosted | No assessment data leaves the platform; no per-token cost |
| Model | `llama3.1:8b`, chosen by benchmark over `qwen2.5:7b` (100% vs 60% correct next step) | Must handle English, structured JSON output and the 10 s turn limit on demo hardware |
| Role of the LLM | Interpret answers, phrase follow-ups and clarifications only | Small local models are unreliable at orchestration; decisions must be explainable |
| Decisions | Deterministic rules in code, each with a `rule:` id | Same input gives the same result; every decision is traceable |
| Structured output | Pydantic models + Ollama JSON-schema `format`, temperature 0 | No free-text parsing; invalid output is retried, then degraded |
| Session memory | LangGraph checkpointer keyed by assessment id; Postgres in the backend | Sessions survive closing the browser or restarting the server |
| Traces | One record per decision, fields of the AGRC-15 trace schema | Explainability (E0-06, HU-25) |
| Degradation | Keyword interpretation + template follow-ups, flagged for human review | The interview never stops if the model is down or slow |
| Interview language | English | Team decision; prompts and knowledge base carry a language code |

## Architecture

The LLM never decides an assessment outcome: it turns a free-text answer into structured fields and phrases what the agent says, and Python rules decide what happens next.

```
START → ask_question → wait_for_answer → interpret (LLM) → decide (rules.py) ─┬─ clarify (LLM) ───┐
             ▲                                                                 ├─ follow_up (LLM) ─┤→ wait_for_answer
             └──────────── next question ──────────── close_control ←─ close ──┘
                                                          └── no questions left → END
```

Every step writes a trace. If Ollama is down or slow, interpretation falls back to keywords and follow-ups to templates, flagged for human review.

A plain "no" closes the control at once; a vague or partial answer loops back through up to three follow-ups before the rules close it.

| Component | File | Responsibility |
| --- | --- | --- |
| Graph | `graph.py` | LangGraph state machine; `interrupt()` waits for the participant |
| Steps | `nodes.py` | Ask, interpret, clarify, follow up, close; each writes its trace |
| Rules | `rules.py` | Next action, what is missing, status, human-review flag |
| LLM client | `llm.py` | Ollama call with JSON schema, timeout, retry, timing |
| Prompts | `prompts.py` | Versioned prompts and template fallbacks |
| Knowledge base | `data/kb_demo.yaml` | Provisional questions + CSF mappings, until E0-03 |
| Traces | `trace.py` | Decision records in the AGRC-15 schema |

## LLM selection

`llama3.1:8b` is selected: it routed all 20 test cases to the correct next step, against 12 of 20 for `qwen2.5:7b`. Its latency still has to come down to meet the 10 s turn limit. `qwen2.5:7b` was the provisional default before the benchmark.

**Method.** `scripts/benchmark_models.py` runs each candidate on `evals/interpret_cases.yaml`: 20 labelled answers covering a detailed yes, a vague yes, partial, no, unsure, not applicable, clarification requests, off-topic answers and multi-turn dialogues. For each case it checks four fields against the label (intent, category, specificity, and the action the rules derive from them) and records latency. Same prompt version, temperature 0, same machine.

**Results** (20 cases, prompt v0.2.0, run on 2026-10-08; details in `evals/results/`):

| Model | Intent | Category | Specificity | Action | Invalid / failed | p50 latency (ms) | p95 latency (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **llama3.1:8b** | 95% | 82% | 92% | **100%** | 0 | 6,485 | 8,846 |
| qwen2.5:7b | 95% | 59% | 62% | 60% | 0 | 5,798 | 7,281 |

**Finding.** `llama3.1:8b` wins on every accuracy field except intent, where both score 95%. `qwen2.5:7b` mislabels category and specificity often enough to send 8 of 20 answers down the wrong path (an unneeded follow-up, or a control closed too early). Both models always returned valid JSON. `qwen2.5:7b` is only about 0.7 s faster at the median, which does not compensate.

**Latency is the open problem.** One call takes 6.5 s at the median and 8.8 s at p95. That p95 is already above the 8 s client timeout, so about 1 in 20 calls would fall back to keywords. A turn with a follow-up makes two calls, about 13 s at the median: over the 10 s target.

Levers to try before changing model, in order of expected effect:

1. Shorten the output: `rationale` and `summary` are free text, and generated tokens dominate latency. Cap them at one short sentence, or drop `summary`.
2. Keep the model loaded (`keep_alive`) and warm it up at session start, so no turn pays the load time.
3. Use the template follow-ups by default and call the LLM to phrase them only when the template cannot quote the participant: one call per turn instead of two.
4. Re-run the benchmark on the demo machine; numbers on another machine do not carry over.

Hardware used: MacBook Air M4, 16 GB unified memory. The 8B model fits comfortably, so the latency comes mainly from generation time; shortening the output is the main lever.

**Selection criteria**, in order:

1. Action accuracy: it decides what the participant experiences next.
2. Zero invalid outputs at temperature 0.
3. p95 per call low enough that a full turn stays within 10 s. A turn can make two calls (interpret, then phrase a follow-up), so the target per call is about 4–5 s.
4. Smaller model wins a tie: cheaper hardware for the demo and for Aligo.

The labels are the team's judgement and should be reviewed with Aligo; results are only as good as the labels.

## Session memory

The interview state lives in a LangGraph checkpointer keyed by `thread_id` = the assessment id, so an assessment can be paused and resumed across sessions and people (HU-09).

- **What is stored:** current question, follow-ups used, full transcript, the last interpretation and decision, and the closed results.
- **How a pause works:** the graph stops at `interrupt()` while waiting for an answer; the checkpointer saves the state. Resuming with the same `thread_id` continues at the exact point.
- **Context after resuming:** the interpreter always receives the whole dialogue about the current question, so follow-ups still refer to earlier answers.
- **Storage:** `MemorySaver` (in-process) in the proof of concept; the Postgres checkpointer (`langgraph-checkpoint-postgres`) in the backend, in the same database as the rest of the schema.

The checkpoint is working state, not the record of truth. Answers, results and traces are also written to their own tables (`interview_turns`, `question_responses`, `control_results`, `decision_traces`), which are isolated per organization.

## Data policy

No assessment data is sent to external APIs. All LLM and embedding calls go to models served by Ollama on infrastructure the platform controls.

| Data | May leave the platform? | Treatment |
| --- | --- | --- |
| Interview answers and transcripts | No | Processed only by the local model; stored per organization |
| Uploaded documents and extracted text | No | Local parsing and local embeddings (vectors in pgvector) |
| Microsoft 365 configuration exports | No | Same as documents |
| Findings, results, traces | No | Stored per organization; exported only by a consultant, as a file (JSON/PDF) |
| Model weights and packages | Downloaded in | Pulled from the Ollama library and PyPI; nothing is uploaded |
| Synthetic test data (eval sets, Aligo samples) | Only if the team decides to compare against a hosted model | Never mixed with client data |

Rules:

1. **Ollama Cloud and hosted LLM APIs are not used** for client data. They would send data outside the platform even on a free tier.
2. Using a hosted model for any client data requires a new decision record approved by Aligo, plus redaction of names, emails, domains and asset names before sending.
3. The demo uses synthetic data only (backlog assumption).

## Cost per assessment

API cost per assessment is zero: the model runs locally. The real cost is model compute time on the machine that hosts Ollama.

```
compute time = questions × calls per question × p50 latency per call
```

With the measured `llama3.1:8b` median of 6.5 s per call: 80 questions × 2.5 calls (interpretation, plus follow-ups and clarifications) × 6.5 s ≈ 22 minutes of compute per assessment, spread over the sessions. The latency levers in LLM selection would lower this too.

- **Demo / development:** a team laptop (16 GB RAM or more is advisable for a 7–8B model). No extra cost.
- **Hosted for Aligo:** one GPU machine or a recent Apple Silicon machine can serve one interview at a time within the latency target; concurrency needs to be measured before sizing.

Open question: the number of questions per assessment depends on the knowledge base (E0-03); replace 80 with the real count.

## Degradation mechanism

If the model fails, times out or returns invalid output, the interview continues with deterministic fallbacks and the affected decisions go to human review.

| Failure | Detection | Fallback |
| --- | --- | --- |
| Ollama down, model not pulled, connection error | Exception from the client | Keyword interpretation; template follow-up |
| Call exceeds the timeout (default 8 s, `AGRC_LLM_TIMEOUT_S`) | Client timeout | Same as above |
| Output fails schema validation | Pydantic error | 1 retry (`AGRC_LLM_RETRIES`), then the fallback |
| Follow-up is not one short question | Must end in "?" and be under 400 characters | Template follow-up that quotes the participant |
| Clarification fails | Exception | Static explanation stored with each question |

Keyword interpretation always reports confidence 0.3 and never claims a detailed answer. Any control closed on top of it, or on any interpretation below 0.5 confidence, is marked `requires_human_review`. The trace records `fallback_used: true` and `prompt_id: rule:keyword_fallback`, so the consultant can see which decisions were degraded.

## Explainability and traces

Every decision the agent makes is written as an append-only trace, so a consultant or administrator can reconstruct why a control got its status.

| Decision type | Written when | Key content |
| --- | --- | --- |
| `answer_interpreted` | After each participant answer | The interpretation, the next step and the `rule:` id applied |
| `evidence_requested` | When a follow-up asks for evidence | The request text and evidence examples from the knowledge base |
| `status_assessed` | When a control is closed | Status, reason, follow-ups used, supporting turns, human-review flag |

Each trace carries the fields of the AGRC-15 trace schema: `organization_id`, `assessment_id`, `control_ids`, `module`, `sources` (the interview turns that support it), `model_name`, `prompt_id`, `prompt_version`, `kb_version`, `output`, `rationale`, `confidence`, `requires_human_review`. Two extra fields help E0-04: `latency_ms` and `fallback_used`. Prompts are versioned, so results can be compared across prompt changes.

The proof of concept writes JSONL files; the backend writes the same records to `decision_traces`.

## Acceptance criteria and open items

Three of the four E0-04 criteria are met; the cost estimate closes once the knowledge base gives the real question count.

- [x] Orchestration library, LLM and session-memory strategy decided and documented (`llama3.1:8b`; latency still to tune)
- [x] Written policy on what data may leave for external APIs and its treatment
- [ ] Cost estimate per complete assessment (measured latency in; needs the real question count)
- [x] Degradation mechanism defined for LLM failure or timeout

Open questions for the team and Aligo:

- Rule for an unsupported "yes": after 3 follow-ups it closes as `not_assessed` with human review, never as compliant. Does Aligo agree?
- The backlog and brief assumed Spanish; the interview is now English. Do reports follow the interview language?
- Labels in the evaluation set need review by someone with GRC experience.
- Demo hardware: which machine runs Ollama for the recorded demo (HU-27)?

Next steps: switch the default model to `llama3.1:8b` and apply the latency levers, then re-run the benchmark on the demo machine; move `agent/` to `backend/app/agent/` once the backend is merged; then contradiction detection (HU-07).
