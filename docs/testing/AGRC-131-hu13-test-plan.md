# AGRC-131 — HU-13 evidence-based completion test plan

Status: planned, **not executed**. HU-13 (AGRC-123) has no implementation in `main` yet. Do not count these cases as passed or mark AGRC-131 Done until the automated and deployed checks below have run.

## Scope and test data

HU-13 lets a representative decide whether a proposed answer derived from an uploaded document should answer a previously unanswered control. A proposal is not an answer or a final result until the representative acts. Consultant review still determines whether a resulting draft becomes final.

Use synthetic content with unmistakable, different phrases:

- Organization A, assessment A1, control PR.AA-03: upload the assessment-specific `backend/tests/fixtures/hu13/a1-mfa.txt`, whose relevant passage contains `TEST-131-A1`. Record the file ID, passage location and proposal ID/reference when the API exposes them.
- Assessment A2 in organization A: upload the separate assessment-specific `a2-mfa.txt`, with a different but equally relevant `TEST-131-A2` passage. A document explicitly shared with all of organization A is allowed in both assessments; do not use a shared document for the A1/A2 isolation assertion.
- Organization B: upload its own relevant `b-mfa.txt` containing `TEST-131-B`. This must not appear in organization A.
- An unrelated `a1-unrelated.txt` document in A1 with no relevant passage for PR.AA-03.
- Representative and consultant accounts with membership in organization A; a separate organization B account for isolation checks.

Create a fresh assessment or restore a transaction-isolated fixture for each decision path. Do not reuse a control whose result was already saved, since current interview result-version rules can otherwise mask a duplicate or block a second path with 409. Keep all file and answer text synthetic.

## Acceptance matrix

| Case | Given / action | Automated assertion | Deployed check |
| --- | --- | --- | --- |
| C1 Confirm | An unanswered A1 control has a proposal backed by the A1 passage; the representative confirms it. | Exactly one approved participant answer is persisted with the confirmed text and a reference to that document passage. Any draft result produced for the control points to the approved answer; it is not final before consultant review. | Confirm the proposal as Representative; reopen the interview and inspect the saved answer and its source. Check the result in Expert reviews as Consultant. |
| C2 Edit | The representative changes the proposed answer to a distinct phrase before approving. | The persisted participant answer and any draft use the edited phrase, never the original proposal text. The recorded decision is an edit, with provenance retained according to the HU-13 API contract. | Edit and approve a proposal, reload, then compare saved answer, Expert reviews and report preview after consultant review. |
| C3 Reject | The representative rejects a proposal for an unanswered control. | No participant answer or control result is created from that proposal; the control remains unanswered. The interview can advance or resume and accept a later genuine answer. | Reject, navigate or resume, and verify the next interview step is usable. |
| C4 No match | A document contains no passage relevant to the unanswered control. | The system does not offer a completion proposal or silently create an answer/result for that control. | Upload/link the unrelated synthetic file and verify no completion is offered. |
| C5 Isolation | A1 has a relevant assessment-specific file; A2 and organization B have different files. | A1 proposals contain neither A2-only nor B files; A2 proposals contain no A1-only file; B cannot access A's proposal or decision resource. Organization-wide shared A files may be offered in A1 and A2, never B. | Check A1 and A2 as the A representative; check B under its own account without exposing A's data. |
| C6 Repeat | The representative repeats the same decision, including a retry after an uncertain response. | The same action cannot create a second participant turn, approved answer, source association or result version. Verify persisted row counts/identifiers, not just HTTP status. A distinct conflicting second decision must also leave the first approved answer intact. | Retry once or reload and repeat where the UI permits; check one saved answer and one review item. |
| C7 Unconfirmed is pending | The document matcher has proposed a passage but the representative has not approved it. | Expert review has no finalizable answer from this proposal; report preview and JSON/PDF exports do not present it as a final result. Pending or proposed UI may identify it explicitly as unconfirmed. | Before acting, inspect Expert reviews and Reports as Consultant; verify the proposal is never labeled as a final answer. |
| C8 Reviewed result | The representative confirms or edits and the consultant then accepts/modifies/rejects the resulting draft. | Report preview, JSON and PDF follow the existing review decision, with the approved or edited answer/source reflected only where appropriate; rejected drafts remain non-final. | Complete one accepted path and inspect the report and downloads. Do not infer verification of a document merely from its citation. |

## Implementation points when AGRC-123 arrives

1. Use a backend acceptance module under `backend/tests/acceptance/` with the project's PostgreSQL transaction fixture, an HTTP client, synthetic uploads and distinct organization/assessment memberships. Exercise the actual HU-13 decision API and persistence rather than creating the confirmed answer directly in the database. A deterministic matcher/agent can replace inference; keep authorization and database behavior real.
2. Add focused frontend tests for the Representative confirm/edit/reject controls, loading/error states and repeated clicks. Assert the outgoing decision payload and the visible state after reload. Existing InterviewWorkspace and ExpertReviewWorkspace tests are useful examples, but a mocked response alone cannot establish persistence or isolation.
3. Reuse report and expert-review assertions from existing tests. Check preview and JSON structures directly; for PDF, extract text or use the project's PDF test helper and assert the relevant final/non-final wording. Verify the same assessment/control across all three outputs.
4. Map the delivered HU-13 endpoint and fields to C1–C8 before writing tests. In particular, record how proposal identity, edited text, passage provenance and replay/idempotency keys are represented. Keep response codes flexible where the requirement specifies the resulting state rather than an exact status code.
5. Run targeted acceptance and frontend tests, then their relevant full suites and build. Record command, counts, commit, CI URL and any skipped cases; a skipped PostgreSQL test is not evidence of a pass.

## Deployed run and evidence

After AGRC-123 and AGRC-131 merge and the deployment is confirmed, run C1–C8 on the public application with synthetic accounts and separate fresh assessments. Capture the proposal with its source, the Representative's decision, the saved answer after reload, the Consultant review state, and report preview plus JSON/PDF. For C5, record which file is assessment-specific and which is organization-wide. For C6, compare IDs/counts before and after the retry. Link screenshots and redacted API/CI outputs in one QA `Test Runs` entry, and open a `Defects` row only for an observed failure.

AGRC-131 can be Done only after all required outcomes are verified, automated checks pass, and the deployed run is recorded. If HU-13 does not provide a way to inspect one of these outcomes, document the gap and agree on the observable contract before claiming coverage.
