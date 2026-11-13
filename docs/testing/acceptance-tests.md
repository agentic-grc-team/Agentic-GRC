# Acceptance tests

Acceptance tests check a user story against its acceptance criteria, end to end through the HTTP API and PostgreSQL. Each test is named after its story and criterion (`test_hu04_ac1_...`), and its docstring holds the Given / When / Then text, so every result traces back to the story. Only the Supabase login is replaced by a fixed user.

Run them from `backend/` with a PostgreSQL test database configured (they are skipped without one):

```
python -m pytest tests/acceptance -v
```

CI runs them in the "Backend tests" job on every pull request.

## HU-04 — Create and scope a security assessment

Jira: AGRC-80 · Task: AGRC-65 · Implementation: AGRC-73, AGRC-62, AGRC-63 · Test file: `backend/tests/acceptance/test_hu04_create_and_scope_assessment.py`

| AC | Given / When / Then | Test | Result |
| --- | --- | --- | --- |
| 1 | **Given** a user has no active membership in the selected organization, **when** the user attempts to open or create an assessment for that organization, **then** access is denied and assessment data is not loaded. | `test_hu04_ac1_non_member_is_denied_and_gets_no_assessment_data` | Pass |
| 2 | **Given** an authorized organization member selects an organization, **when** the member creates an assessment, **then** the selected organization and assessment scope are shown clearly before the interview starts. | `test_hu04_ac2_scope_is_shown_before_the_interview_starts` | Pass |
| 3 | **Given** an assessment has been created with selected NIST CSF 2.0 functions or categories, **when** the member opens the assessment summary, **then** only the selected in-scope domains and controls are shown. | `test_hu04_ac3_summary_shows_only_in_scope_domains_and_controls` | Pass |
| 4 | **Given** an assessment is saved, **when** the member reopens it, **then** its assessment date and framework or knowledge-base version remain available. | `test_hu04_ac4_date_and_versions_remain_available_on_reopen` | Pass |

What each test checks:

1. A member of another organization and a suspended member get 404 with no assessment data when listing, opening, reading the scope of, or creating an assessment; no assessment is created.
2. A consultant creates an assessment; the consultant and a representative both see the organization and the scope (PR → PR.AA → PR.AA-01, PR.AA-03, PR.AA-05 with the official CSF 2.0 wording). A representative cannot create an assessment (403).
3. A control added as out of scope (DE.CM-01) is not shown; only the three in-scope controls and their function are listed. Note: the consultant does not select functions or categories when creating an assessment yet. The scope comes from the knowledge-base version (demo-0.2: PR.AA-01, PR.AA-03, PR.AA-05), so this criterion is checked against that fixed scope; selecting the scope is not implemented.
4. Reopened by another member through a new client, the assessment, its scope and the assessment list all return the same start date, NIST-CSF 2.0 and KB version demo-0.2.

Each test was also checked against a deliberately broken implementation (scope without the in-scope filter, scope endpoint without the access check, no controls on creation, representatives allowed to create); the matching test failed every time.

Recorded runs:

| Date | Where | Result |
| --- | --- | --- |
| 2026-10-24 | Local, PostgreSQL 16, all migrations | 4 passed |
| 2026-11-01 | Local, PostgreSQL 16, all migrations | 4 passed |
| 2026-11-09 | CI (Backend tests job), PostgreSQL 16, all migrations (Sprint 5 main) | 4 passed |

## HU-17 — See the gaps ordered by criticality

Story: as a security officer at the assessed organization, I want to see the gaps ordered by criticality, so that I know where to start when I cannot tackle them all.

Implementation: part 1 (#47, `backend/app/services/risk_classification.py`) · Unit tests: `backend/tests/test_risk_classification.py` · Acceptance tests: planned, after part 2 connects the classification to the HU-16 gap findings.

The classification follows Aligo's classification guide (handover `06_classification`). Priority (Critical, High, Medium, Low) belongs to the control, not to its status. Each gap carries one or more named risks, and each risk has a fixed severity (Extreme, High, Medium, Low). The current rules for PR.AA-01, PR.AA-03 and PR.AA-05 are provisional: the PO confirmed them for the Alpha and the Beta, and they stay marked as provisional until Aligo confirms them.

| AC | Given / When / Then | Covered now (unit level, part 1) | Acceptance test |
| --- | --- | --- | --- |
| 1 | **Given** an assessment with control results, **when** the security officer views the gaps, **then** only controls whose result is partially implemented or not implemented are listed as gaps, and implemented, not applicable and not assessed controls are not. | `test_a_control_that_is_not_a_gap_gets_no_classification` | Planned |
| 2 | **Given** several gaps, **when** the security officer views them, **then** they are ordered by priority (Critical first), then by their most severe risk (Extreme first), then not implemented before partially implemented, then by control code, and the order is the same every time. | `test_gaps_are_ordered_by_priority_first`, `test_equal_priority_is_ordered_by_the_most_severe_risk`, `test_equal_priority_and_risk_puts_not_implemented_first_then_control_code` | Planned |
| 3 | **Given** a gap, **when** the security officer views it, **then** it shows its priority, its risks with their severity and the reason for the priority, it is marked as provisional while the rules are provisional, and the classification is recorded as a decision that cites the control result it is based on. | `test_a_gap_gets_the_control_priority_and_its_risks_most_severe_first`, `test_classification_trace_is_a_valid_rule_decision`, `test_classification_trace_without_a_source_is_rejected` (citing the control result in the sources is planned) | Planned |
| 4 | **Given** a gap whose control has no classification rule, **when** the gaps are listed, **then** that gap is shown as not classified, without an invented priority, and the other gaps are still listed in order. | `test_a_control_without_a_rule_is_refused_instead_of_given_a_priority` (the rule itself refuses; the listing part is planned) | Planned |
| 5 | **Given** a user without access to the organization or assessment, **when** they request the gaps, **then** access is denied and no gap data is disclosed. | — | Planned |

Notes:

- AC 1 to 3 are already true for the classification function itself (unit tests above). The acceptance tests will check the same criteria through the API, once the gaps come from the HU-16 findings.
- AC 4 follows the PO's review note on #47: the classification function refuses a control without a rule, and the caller shows that gap as not classified instead of failing the whole list.
- Only the four risks with a severity in Aligo's materials are assigned (Unauthorized access, System compromise, Privilege escalation, Improper assignment of privileged functions). The other four risk names in the guide wait for Aligo to give their severity.

## HU-25 — Inspect reasoning traces and source references

Jira: AGRC-82 · Task: AGRC-65 · Implementation: AGRC-60 (trace view), AGRC-72 (persisted trace references) · Test file: `backend/tests/acceptance/test_hu25_inspect_reasoning_trace.py`

In every test the assessment is created through the API and a representative answers the first interview question, so the agent saves a real draft result with its decision trace. The language model is replaced by a deterministic fake.

| AC | Given / When / Then | Test | Result |
| --- | --- | --- | --- |
| 1 | **Given** an authorized administrator or expert opens a result, **when** the trace view is selected, **then** the assessment, control, result version, and organization context are identifiable. | `test_hu25_ac1_result_context_is_identifiable` | Pass |
| 2 | **Given** a trace is available, **when** the authorized reviewer opens it, **then** the view shows the trace steps and source references linked to the result. | `test_hu25_ac2_trace_steps_and_source_references_are_shown` | Pass |
| 3 | **Given** no trace exists or trace loading fails, **when** the view is opened, **then** the user sees a clear unavailable state and the system does not display a fabricated trace. | `test_hu25_ac3_no_trace_gives_an_unavailable_state_and_nothing_is_invented` | Pass |
| 4 | **Given** the user lacks access to the organization or assessment, **when** they request a trace or export, **then** access is denied and trace data is not disclosed. | `test_hu25_ac4_users_without_access_get_no_trace_data` | Pass |

What each test checks:

1. The consultant of the organization and a platform administrator open the agent's draft and see the organization (id and name), the assessment (id and title), the control (code and title), version 1 and author "agent". After the consultant corrects the draft, the trace of the new result shows version 2 and author "aligo_consultant".
2. The steps are the recorded decisions for this control in this assessment, oldest first. The decision that produced the result is among them (`status_assessed`, with the result's status), and its source reference is `interview_turn:<id>` of the representative's answer, which is stored in the same organization with the answer text.
3. A result with no linked decision returns its context, no linked decision and no steps: decisions of the other control are not borrowed. An unknown result is "not found", not an empty trace. The screen side is covered by `ReviewTrace.test.jsx`: "says clearly when no decision is linked and does not invent one", "warns when the linked decision is missing from the steps" and "shows an unavailable state on failure and retries with the latest token".
4. A consultant of another organization and a suspended consultant get 404, and the organization's representative gets 403 (HU-03), for the result trace, the assessment traces and the trace export. No response contains a trace id or the answer text. Asking with the outsider's own organization and this assessment's id returns no traces.

Each test was also checked against a deliberately broken implementation (steps not filtered by control, no access check on the result trace, representatives allowed to read traces, a fixed result version, the result's own decision left out); the matching test failed every time.

Recorded runs:

| Date | Where | Result |
| --- | --- | --- |
| 2026-11-01 | Local, PostgreSQL 16, all migrations | 4 passed |
| 2026-11-09 | CI (Backend tests job), PostgreSQL 16, all migrations (Sprint 5 main) | 4 passed |

### Sprint 5 validation

Checked on 2026-11-09 against main after #36 (Ollama warm-up), #39 (evidence attached to controls), #40 and #43.

- The four HU-25 acceptance tests pass, and so do the 12 screen tests in `ReviewTrace.test.jsx`.
- The trace code did not change in Sprint 5. The trace endpoints (`traces.py`, `expert_reviews.py`), the trace services and schemas, and `ReviewTrace.jsx` are the same as at the end of Sprint 4. The only Sprint 5 changes in related services are two model settings in `interview_agent.py` (#36) and attaching evidence to controls in `evidence_links.py` (#39). Neither changes how traces are recorded or shown.
- All four criteria are still met as tested above.

Known limits, not covered by the criteria:

- Agent decisions cite interview answers only (`interview_turn` sources). Evidence attached to a control (#39) appears in the Expert Review evidence panel, not as a step or source in the trace.
- The criteria were checked by the automated tests. They have not been checked on a deployed environment, because none exists yet.

Checks for the end-to-end test on the deployed environment (one per criterion, done in the browser):

| AC | Check |
| --- | --- |
| 1 | As the consultant, open an agent draft in Expert Review and open its trace. Organization, Assessment, Control and "Result version 1 (AI draft)" are shown. After correcting the draft, the trace shows "2 (Consultant version)". |
| 2 | The trace lists the decisions for that control, oldest first, including "Status assessed", and its source points to the representative's answer. |
| 3 | A result without a linked decision shows "No recorded decision is linked to this result version." and no invented steps. |
| 4 | Signed in as the organization's representative, no trace content (steps, answer text) is shown. |
