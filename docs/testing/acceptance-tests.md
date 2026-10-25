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
3. A control added as out of scope (DE.CM-01) is not shown; only the three in-scope controls and their function are listed.
4. Reopened by another member through a new client, the assessment, its scope and the assessment list all return the same start date, NIST-CSF 2.0 and KB version demo-0.2.

Each test was also checked against a deliberately broken implementation (scope without the in-scope filter, scope endpoint without the access check, no controls on creation, representatives allowed to create); the matching test failed every time.

Recorded runs:

| Date | Where | Result |
| --- | --- | --- |
| 2026-10-24 | Local, PostgreSQL 16, all migrations | 4 passed |

## HU-25 — Inspect reasoning traces and source references

Jira: AGRC-82 · Task: AGRC-65 · Implementation: AGRC-60. Planned after the Alpha presentation.
