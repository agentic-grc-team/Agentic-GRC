# HU-12: document passages relevant to controls

| Field | Value |
| --- | --- |
| Story | HU-12 (AGRC-122): identify document passages relevant to controls |
| Implementation | `backend/app/services/passage_matching.py`, `GET .../assessments/{assessment_id}/passage-matches` |
| Owner | Mihailo |
| Used by | HU-13 answer proposals (AGRC-129, Natalia), the consultant's passage view (Miloš), HU-12 tests (AGRC-128, Abedin) |
| Status | Matcher `lexical-0.1`; acceptance criteria below are proposed by the PO |

## What it does

For one assessment, the text extracted from each uploaded evidence file is split into passages, and each passage is checked against each in-scope control. A match says which file and which control, where the passage is, a literal excerpt, which terms matched and how confident the matcher is.

The files checked are the organization's files of this assessment and its files that belong to no assessment, the same files that can be linked to the assessment's controls. Other assessments and other organizations are never read.

Matches are computed on demand and not stored: there is nothing to keep in sync when a file is uploaded or a matcher changes, and the same text always gives the same matches. `matcher_version` tells one matcher apart from the next. Nothing is written to the decision trace, because reading matches is not a decision; HU-13 records `evidence_extracted` when it creates a proposal from a match.

## A match is not evidence

A match only says that a passage is about a control. It never says the control is implemented: a policy proves intent, not implementation (Aligo's evidence rubric), and only a consultant verifies evidence. So matches:

- never link a file to a control by themselves. `linked` shows whether someone already did, so the consultant can link the file with the existing `POST /evidence/{id}/controls`;
- never change a control result, and never count as `evidence_refs`;
- are the input of HU-13, where the representative confirms an answer before it is used.

## How passages are matched (`lexical-0.1`)

- **Passages.** A passage ends at a blank line, a heading, a page break or about 700 characters. Wrapped PDF lines of one paragraph stay together. A heading (numbered like `3.2 Access Review`, in capitals, or a short line ending with a colon) becomes the `section` of the passages under it. A short line in Title Case is not taken as a heading, because it may be a sentence without a final period and would then never appear in an excerpt.
- **Terms.** Each control has core terms and supporting terms, in English and Spanish (clients upload Spanish policies). Text and terms are compared in lower case without accents, as whole words, allowing hyphens and plurals: `Autenticación multifactor` matches `autenticacion multifactor`, and `multi-factor` matches `multi factor`.
- **Match.** A passage matches a control only when it is about the control itself: it has a core term of its own, or a supporting term under a heading that has a core term. A heading never makes a match on its own (a date under an `MFA` heading is not MFA evidence), and supporting terms alone (`employee`, `quarterly`, `administrator`) never make a match either.
- **Confidence.** One core term gives 0.55; each further core term or supporting term (up to three) adds 0.1, capped at 0.95. It is a ranking signal, not a calibrated probability. For HU-13 we suggest a threshold of **0.65**, a core term plus one more signal, rather than 0.6.
- **Limits per file.** At most three passages per file and control, most confident first.
- **Controls without terms.** An in-scope control without terms gets no match and is listed in `controls_without_terms`, so "no terms yet" is never read as "no relevant passage". Today only the demo controls PR.AA-01, PR.AA-03 and PR.AA-05 have terms; a test checks that every control in the knowledge-base scope has them.

## The match contract (answers D1 in the HU-13 design)

| Field | Notes |
| --- | --- |
| `organization_id`, `assessment_id` | Always the requested organization and assessment |
| `assessment_control_id`, `control_code` | The in-scope control |
| `evidence_file_id`, `file_name` | The uploaded file |
| `reference` | `document_span:<file id>`, with `#page=<n>` when the page is known (trace-schema format) |
| `locator` | `page` (null when unknown), `section` (nullable), `char_start`, `char_end` (end exclusive) in the file's `extracted_text` |
| `excerpt` | Literal passage text, whitespace collapsed, at most 300 characters around the first core term |
| `matched_terms` | Core terms first, then supporting terms: the explanation of the match |
| `confidence` | 0–1, see above |
| `matcher_version` | `lexical-0.1` |
| `verification` | Always `not_verified`: a match is a suggestion, never verified evidence. Same marker as linked files in the report ("Not yet verified by Aligo") |
| `linked` | The file is already linked to this control. Linking does not verify it either |

This is the contract in section 2 of `hu13-evidence-answer-proposals.md`, plus `control_code`, `file_name`, `reference`, `matched_terms`, `verification` and `linked`.

## Pages

Since HU-12, PDF pages are joined with a form feed (`\f`) in `extracted_text`, so a passage knows its page. Files uploaded before, single-page PDFs and DOCX/TXT/CSV/XLSX files have no page breaks: their `page` is null and the `section` and character range locate the passage.

## Proposed acceptance criteria (PO)

| AC | Given / When / Then |
| --- | --- |
| 1 | **Given** an uploaded document with a passage about an in-scope control, **when** a member asks for the assessment's passage matches, **then** the passage is listed for that control with the file, its location (page when known, section, character range) and a literal excerpt of at most 300 characters. |
| 2 | **Given** a match, **when** it is shown, **then** it states the terms that matched, a confidence and the matcher version, so the consultant can see why it was proposed. |
| 3 | **Given** English and Spanish documents, **when** they are matched, **then** both languages are recognised, accents included. |
| 4 | **Given** a document with no passage about a control, **when** the matches are listed, **then** no match is invented for that control. |
| 5 | **Given** a match, **when** it is listed, **then** it is not treated as verified evidence: no file is linked and no result changes until a person acts. |
| 6 | **Given** a user without an active membership in the organization, or documents of another organization or assessment, **when** matches are requested, **then** the user gets 404 and no other organization's or assessment's document is read. |

The tests for these criteria are `backend/tests/test_passage_matching.py` (matcher) and `backend/tests/test_passage_matching_api.py` (API, PostgreSQL). The acceptance tests through the whole flow are AGRC-128.

## Not in this version

- Text inside DOCX tables is not extracted, so passages in tables are not matched yet.
- Lexical matching misses paraphrases that use none of the terms. An embedding or model-based matcher can replace it behind the same contract with a new `matcher_version`, measured on an eval set (the Halverston corpus in Aligo's handover is a good base).
- No screen yet; the consultant view is Miloš's task.
