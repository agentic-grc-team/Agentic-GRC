# Agent–API contract

| Field | Value |
| --- | --- |
| Sprint 4 | S4-P01 (interview API and persisted results) |
| Owners | Agent: Natalia · Interview API: Santiago |
| Status | Draft, describes the interface merged in PR #28; open decisions in section 7 |

## 1. Who owns what

The interview API runs the agent; neither side reaches into the other's internals.

| Interview API (`app/services/interviews.py`, `interview_agent.py`) | Agent (`app/agent/`) |
| --- | --- |
| Authentication, roles, organization scoping | Interview graph, rules, prompts, fallback |
| Sessions, participants, saved turns, idempotency keys | Interpreting answers and deciding the next step |
| Choosing the questions and in-scope controls for a session | Wording of questions, follow-ups and clarifications |
| Writing turns, traces and results to the database | Producing turns, traces and results in the graph state |
| The LangGraph checkpointer and its connection | Keeping the graph state JSON-compatible |

## 2. Entry points the API calls

`app/services/interview_agent.py` is the only code that imports the agent.

| Function | When | Returns |
| --- | --- | --- |
| `start_interview_agent(db, session_id)` | A session is opened or resumed | The agent turns created by this call |
| `advance_interview_agent(db, organization_id, assessment_id, session_id, answer_turn_id)` | A participant answer has been saved | The agent turns created by this call |

Both hold a row lock on the session while the graph runs, so answers to one session are processed one at a time.

From the agent package the service uses only:

| Agent API | Purpose |
| --- | --- |
| `load_kb(path)` | Read the knowledge base (`app/agent/data/kb_demo.yaml` until E0-03) |
| `initial_state(organization_id, assessment_id, question_codes, in_scope_control_codes, kb_version)` | First state of a session |
| `Deps(llm, kb, tracer, max_follow_ups)` and `build_graph(deps, checkpointer)` | Build the graph |
| `OllamaLLM(model, host, timeout_s, retries)` | The model client; tests replace it with `FakeLLM` |

## 3. Graph state the API reads

The graph pauses with `interrupt({"message": ...})` when it needs an answer, and the API resumes it with `Command(resume=<answer>)`. After each run the API reads these keys from the state:

| Key | Shape | Rule |
| --- | --- | --- |
| `turns` | list of `{seq, question_code, speaker, turn_type, content}` | Append-only; `seq` starts at 1 per session |
| `traces` | list of `DecisionTrace` dumps (trace schema v0.2) | Append-only; sources cite `turn:<seq>` |
| `results` | `question_code` → `ControlResult` dump | One entry per closed question |
| `pending_message` | text | What the agent asks next |

The API maps the agent's identifiers to database identifiers when it saves them:

| Agent | Database |
| --- | --- |
| `turn:<seq>` in trace sources | `interview_turn:<id>` |
| `question_code` | `questions.id` of the assessment's knowledge-base version |
| A `status_assessed` trace | `AgentControlResult.from_agent_output(trace.output)` → `save_agent_result()` |

## 4. Checkpoints

- Postgres checkpointer (`app/services/langgraph_checkpointer.py`), in the private schema `agentic_grc_private`.
- `thread_id` = interview session id, so a session resumes after a restart or from another browser.
- Only JSON-compatible values are stored: the serializer refuses arbitrary Python objects.
- A checkpoint stores the whole graph state. Renaming or removing a state key breaks sessions already in progress (see 7d).

## 5. Failures

| Situation | Behaviour |
| --- | --- |
| Model client cannot be created | API returns 503 |
| A model call fails or returns invalid output | The agent does not raise: keyword interpretation (confidence 0.3) and template questions, `fallback_used: true` in the trace |
| Interpretation confidence < 0.5 | One focused clarification; if still unclear, `not_assessed` with human review. A fallback interpretation therefore never sets a status |
| Knowledge-base version, language or questions do not match the assessment | API returns 409 |

## 6. Changing the contract

- Any change to the state keys in section 3, to `ControlResult` or to `AgentControlResult` needs both owners' review.
- Changing prompt wording bumps its version in `app/agent/prompts.py`; the version is stored in every trace.
- Behaviour changes to the rules are checked with `pytest tests/agent` and `scripts/benchmark_models.py`.

## 7. Open decisions

a. **Re-assessment.** Decided for now (#28): `save_agent_result()` refuses with 409 when a control already has a result, so an agent re-run cannot replace an expert's decision. Still open: a restarted interview (`restart=true`) on an assessment with results gets stuck, because every closing answer returns 409. Either refuse the restart up front or skip the questions whose controls are already assessed.

b. **Evidence requests can exceed the follow-up limit.** A detailed "yes" always gets its evidence request, even after 3 follow-ups, so a question can reach 4. Accept explicitly or keep the limit.

c. **With the model down, every question ends as `not_assessed`.** The keyword fallback always has confidence 0.3, so each question takes two answers and closes for human review, even a clear "no". Safer than before, but the degradation section of ADR 0002 still describes the old behaviour.

d. **Sessions in progress when the agent changes.** Proposal: store an agent version in the state and restart sessions created with an older one, rather than migrating checkpoints.

e. **Two sources for questions.** Question text comes from the database, while intent, required detail, evidence examples and control mappings come from the YAML. Fine for the demo; E0-03 should make the database the only source.
