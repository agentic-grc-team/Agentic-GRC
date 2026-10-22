# Decision Record 0003 — Interview data governance and inference boundary

Status: MVP guardrails accepted; GCP remains a provisional inference target.
Date: 2026-10-20
Backlog: Agentic Interviewing API / Sprint 4

This record supersedes the production-data assumptions in ADR 0002. ADR 0002 remains the record of the local proof of concept and its benchmark; its Ollama selection and “no data leaves the platform” statement are not production decisions.

## Context

The authenticated interview stores participant answers, evidence references, draft findings, trace records, and resumable agent state. The MVP uses one agent. The orchestration library, model, and session-memory strategy must be supported by a documented technical evaluation. Python and LangGraph are the current implementation choices, not a requirement to process client data before that evaluation and the data boundary are approved.

## Decisions

### Inference and topology

- Google Cloud Platform is the provisional target for model inference. This does not select a final model, endpoint, region, or provider configuration.
- Before production-like data is processed, document the complete topology for the web/API tier, model inference, evidence storage, checkpoint storage, and secrets. Record data regions, transfer paths, service identities, and access boundaries.
- Keep model credentials in the deployment secret manager. Do not add credentials, tokens, or connection strings to source control, trace output, prompts, or checkpoints.

### Data allowed during development and evaluation

- Synthetic data is the default for development, demos, and benchmarks.
- Approved anonymized data may be used for testing after the data owner approves the sample and its anonymization.
- Real organizational data is blocked until the external-transfer, retention, deletion, redaction, and storage rules are approved and the topology above is documented.
- This gate applies to transcripts, source excerpts, evidence, draft results, traces, and LangGraph checkpoints. A checkpoint is working state, but it can contain the same sensitive content as a transcript.
- Production interview routes fail closed until all six transfer, retention, deletion, redaction, storage, and topology approvals are configured. A remote model URL must use HTTPS and requires explicit transfer approval and a documented topology. Synthetic-mode free text is not reliably classifiable by the API, so production must not rely on that label instead of the approval gate.
- The API does not perform general-purpose anonymization. Approved anonymized samples must be anonymized before submission; the request validation only rejects a declared non-English language because the configured interview agent currently supports English.

### Persistence and session memory

- PostgreSQL domain tables are the durable record for interview sessions and turns. The LangGraph Postgres checkpointer is resumable working state; it is not the source of truth for saved answers or findings.
- Use the assessment session UUID as the LangGraph thread ID. Checkpoint tables live in the non-exposed `agentic_grc_private` schema and are managed by the official Postgres checkpointer setup routine, separately from Alembic domain migrations.
- Serialize graph state using JSON-compatible values and an empty MsgPack object allowlist. Never place secrets in graph state.
- The existing append-only `decision_traces` table and backend `record_trace()` service are the production trace path. Interview decisions reference turns as `interview_turn:<uuid>` and avoid copying answer text into trace excerpts unless a separately approved redaction policy permits it. JSONL was only a proof-of-concept format.

### Benchmark and failure behavior

- Record cost and latency measurements for each candidate model and deployment configuration. Include at least p50/p95 latency, tokens, errors, timeout rate, fallback rate, and the evaluated task set.
- Do not infer a final cost ceiling from the current backlog or the local Ollama proof-of-concept benchmark.
- On model failure, invalid output, or timeout, continue with deterministic rules and approved templates where possible. Mark affected draft results for expert review; a model failure must not silently produce a final result.

## Production-like data gate

Before lifting the gate, the project must approve and publish:

1. External-transfer terms, model-provider processing and residency.
2. Retention periods and deletion behavior for domain records and checkpoints.
3. Redaction rules for participant answers, evidence excerpts, logs, and traces.
4. Storage and access topology, including the model, evidence store, checkpoint schema, and secret manager.
5. A measured cost/latency benchmark for the selected runtime and the failure/degradation behavior.

Until those decisions are recorded, operate with synthetic data by default and use anonymized data only when specifically approved.
