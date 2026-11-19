# Acceptance tests

Acceptance tests check a user story against its acceptance criteria, end to end through the HTTP API and PostgreSQL. Each test is named after its story and criterion (`test_hu04_ac1_...`), and its docstring holds the Given / When / Then text, so every result traces back to the story. Only the Supabase login is replaced by a fixed user.

Run them from `backend/` with a PostgreSQL test database configured (they are skipped without one):

```
python -m pytest tests/acceptance -v
```

CI runs them in the "Backend tests" job on every pull request.

## HU-02 / HU-03 — Organization isolation and role permissions

Stories: HU-02, as a security officer at the assessed organization, I want my answers, documents and findings to be inaccessible from any other organization. HU-03, as a platform administrator, I want each user to have a role with distinct permissions, so that the representative can answer the interview without being able to alter findings or see the agent's reasoning.

Jira: AGRC-138 · Test file: `backend/tests/acceptance/test_hu02_hu03_role_and_organization_access.py` · Existing cross-organization API tests (AGRC-67): `backend/tests/test_cross_organization_api.py`

The rules as implemented:

| Action | Consultant / administrator | Representative | Member of another organization, suspended member, no membership |
| --- | --- | --- | --- |
| Create an assessment | Yes | No (403) | No (404) |
| Open, read and answer the interview | Yes | Yes | No (404) |
| Upload evidence, list evidence and links | Yes | Yes | No (403) |
| Expert review queue, decision, review evidence | Yes | No (not in the queue, 403) | No (not in the queue, 404) |
| Reasoning traces (result trace, assessment traces, export) | Yes | No (403) | No (404) |
| Report (preview and PDF) and gap list | Yes | Yes | No (404) |

The representative reads the report and the gap list because they are written for the security officer of the assessed organization (HU-17, HU-18, HU-23).

In every test the consultant creates the assessment through the API, the representative opens the interview, answers, uploads the evidence the agent asks for through the interview and answers again, and the agent saves a draft result. The language model is replaced by a deterministic fake.

| AC | Given / When / Then | Test | Result |
| --- | --- | --- | --- |
| 1 | **Given** a consultant with an active membership in the organization, **when** a draft result of that organization waits for review, **then** the consultant sees it in the queue, opens its trace and evidence, and records a decision. | `test_access_ac1_consultant_reviews_in_own_organization` | Pass |
| 2 | **Given** a representative with an active membership in the organization, **when** they answer the interview and upload the evidence the agent asks for, **then** the answers and the evidence are saved for that organization, and the representative cannot see the review queue, record a decision, or inspect reasoning traces. | `test_access_ac2_representative_answers_and_provides_evidence_but_cannot_review` | Pass |
| 3 | **Given** two organizations, each with an assessment, interview, evidence and draft result, **when** a consultant or a representative of organization A uses organization B's identifiers, **then** every interview, evidence, finding, gap list and report request fails with no data, and nothing is written to organization B. | `test_access_ac3_no_role_reaches_another_organization[consultant]`, `[representative]` | Pass |
| 4 | **Given** an assessment whose draft the consultant has accepted, **when** the report and the gap list are requested, **then** the organization's consultant and representative get them, and a member of another organization, a suspended member and a user with no membership get no data. | `test_access_ac4_report_and_gap_list_only_for_members_of_the_organization` | Pass |

What each test checks:

1. The consultant finds the draft in the review queue, opens its trace (with the organization's id), its review evidence and the assessment traces, and accepts it.
2. The representative's two answers and the uploaded file are stored for the organization, the file is linked to the requested control, and the representative can read the interview and list the file. The draft is not in the representative's review queue; the decision, the result trace, the review evidence, the assessment traces and the trace export all return 403. The draft stays version 1 by the agent with no review.
3. For both roles of organization A: B's interview (read, status, open, answer) returns 404, through B's path and through A's path with B's assessment id. Listing B's evidence and links and uploading into B's interview return 403. B's draft is not in the queue; its decision, trace and review evidence return 404. B's gap list, report and PDF return 404 through both paths. Afterwards B has the same number of interview turns, one evidence file and no review.
4. The consultant and the representative get the report, the PDF and the gap list of their assessment. The consultant and the representative of another organization, a suspended consultant of the same organization and a user with no membership get 404 for all three.

Each test was also checked against a deliberately broken implementation (representatives allowed to read traces, report and gap list without the membership check, interview without the membership check, representatives allowed to review, evidence list without the membership check); the matching tests failed every time.

Not covered by these tests:

- Managing memberships (inviting members and choosing their role, `backend/app/api/v1/endpoints/organizations.py`) is not part of AGRC-138; that module stays at 51% coverage.
- Platform administrators are covered by the HU-04 and HU-25 tests, not here.

Recorded runs:

| Date | Where | Result |
| --- | --- | --- |
| 2026-11-19 | Local, PostgreSQL 16, all migrations | 5 passed |

Checks on the deployed Beta (https://gita.udea.edu.co/agentic-grc/), done in the browser with a consultant and a representative of one organization and a user of a second organization:

| AC | Check | Result |
| --- | --- | --- |
| 1 | As the consultant, open Expert Review, open the draft's trace and evidence, and accept it. | Not run yet |
| 2 | As the representative, answer the interview and upload the requested file. The representative cannot review the draft or open its trace. | Not run yet |
| 3 | As the user of the second organization, open the first organization's assessment, interview, report and gap list by URL. Nothing is shown. | Not run yet |
| 4 | As the consultant and as the representative, open the report and the gaps by criticality section. Both are shown. | Not run yet |

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

Jira: AGRC-95 · Implementation: risk classification (#47, `backend/app/services/risk_classification.py`) and the gap list (`GET /api/v1/organizations/{organization_id}/assessments/{assessment_id}/gaps`, `backend/app/services/gaps.py`) and its screen on the Report page (`frontend/src/features/reports/GapList.jsx`) · Test file: `backend/tests/acceptance/test_hu17_gaps_ordered_by_criticality.py` · Unit tests: `backend/tests/test_risk_classification.py`, `backend/tests/test_gaps.py`

A gap is a control whose final result is partially implemented or not implemented. The final result is decided exactly as in the report (HU-21): only results confirmed by a consultant count, so the gap list and the report never disagree, and an agent draft that has not been reviewed is not a gap yet. Access is the same as for the report: active members of the organization, including its representatives (the security officers of this story), and platform administrators. Anyone else gets 404 and no data, as in HU-04 AC 1.

The classification follows Aligo's classification guide (handover `06_classification`). Priority (Critical, High, Medium, Low) belongs to the control, not to its status. Each gap carries one or more named risks, and each risk has a fixed severity (Extreme, High, Medium, Low). The current rules for PR.AA-01, PR.AA-03 and PR.AA-05 are provisional: the PO confirmed them for the Alpha and the Beta, and they stay marked as provisional until Aligo confirms them.

In the tests the assessment is created through the API. AC 3 follows the whole flow: the representative answers in the interview, the agent saves a draft and the consultant accepts it. The other criteria give the controls their final results directly, as a consultant version would. The language model is replaced by a deterministic fake.

| AC | Given / When / Then | Test | Result |
| --- | --- | --- | --- |
| 1 | **Given** an assessment with control results, **when** the security officer views the gaps, **then** only controls whose result is partially implemented or not implemented are listed as gaps, and implemented, not applicable and not assessed controls are not. | `test_hu17_ac1_only_partially_or_not_implemented_controls_are_gaps` | Pass |
| 2 | **Given** several gaps, **when** the security officer views them, **then** they are ordered by priority (Critical first), then by their most severe risk (Extreme first), then not implemented before partially implemented, then by control code, and the order is the same every time. | `test_hu17_ac2_gaps_are_ordered_by_criticality_the_same_way_every_time` | Pass |
| 3 | **Given** a gap, **when** the security officer views it, **then** it shows its priority, its risks with their severity and the reason for the priority, it is marked as provisional while the rules are provisional, and it identifies the control result it is based on. | `test_hu17_ac3_each_gap_shows_its_classification_and_what_it_is_based_on` | Pass |
| 4 | **Given** a gap whose control has no classification rule, **when** the gaps are listed, **then** that gap is shown as not classified, without an invented priority, and the other gaps are still listed in order. | `test_hu17_ac4_a_control_without_a_rule_is_shown_as_not_classified` | Pass |
| 5 | **Given** a user without access to the organization or assessment, **when** they request the gaps, **then** access is denied and no gap data is disclosed. | `test_hu17_ac5_users_without_access_get_no_gap_data` | Pass |

What each test checks:

1. With implemented, not assessed and partially implemented results, only the partially implemented control is a gap. In a second assessment, not applicable is not a gap and not implemented is.
2. With the current rules (all three High, each with an Extreme risk), the not implemented gap comes first, then the others by control code, and a second request gives the same order. Raising one control to Critical puts it first. With equal priority, the gap whose worst risk is only High comes after the ones with an Extreme risk.
3. Before the consultant reviews the agent's draft, the list is empty and the control counts as pending. After the consultant accepts it, the gap shows the rule's priority, its risks sorted from the most severe, the reason, `rules_provisional: true` and `rule:risk-classification`, and it names the result it rests on: version 1, an accepted agent result.
4. With the rule for PR.AA-01 removed, its gap is listed last with no priority, risks or reason, and the other two gaps keep their order.
5. A consultant of another organization and a suspended consultant get 404 with no gap data. Asking with the outsider's own organization and this assessment's id also returns 404.

Each test was also checked against a deliberately broken implementation (not assessed counted as a gap, no ordering, a missing rule failing the list, no membership check, always citing version 1, unreviewed drafts counted as gaps); the matching test failed every time.

Not covered yet:

- The gap list is built from the final control results. When the HU-16 gap findings exist, they become its input, and the classification is then recorded as a decision of each finding (`finding_generated` with `rule:risk-classification`). Until then, every gap is traceable through the rule id and version in the response and the control result version it names.
- Not assessed controls are not gaps, but they stay in the report's reviewed results, where they remain visible for human review.
- Only the four risks with a severity in Aligo's materials are assigned (Unauthorized access, System compromise, Privilege escalation, Improper assignment of privileged functions). The other four risk names in the guide wait for Aligo to give their severity.
- The gap list is shown on the Report page ("Gaps by criticality", `frontend/src/features/reports/GapList.jsx`). The page does not call `/gaps`: the report preview (`GET .../report`) carries the same list as `gap_list`, built from the same report view in the same request, so the list and the report on screen always agree. The PDF and JSON exports do not include it. Its screen tests are in `GapList.test.jsx`; the acceptance tests above check the `/gaps` API, which applies the same rules.
- A rule that names a risk without a confirmed severity is treated like a missing rule: the gap is listed as not classified instead of failing the list.

Recorded runs:

| Date | Where | Result |
| --- | --- | --- |
| 2026-11-15 | CI (Backend tests job), PostgreSQL 16, all migrations | 5 passed |

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
