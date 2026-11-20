# HU-13: answer proposals from uploaded evidence

| Field | Value |
| --- | --- |
| Story | HU-13 (AGRC-123): use uploaded evidence to complete unanswered controls |
| This document | AGRC-129: prepare evidence-based answers (backend) |
| Owners | Proposals (AGRC-129): Natalia · Representative UI (AGRC-130) and acceptance tests (AGRC-131): Milos · Passage matching (HU-12, AGRC-122): Mihailo |
| Status | Draft for review; open decisions in section 8 |

## 1. What AGRC-129 does

For a control in the assessment scope that nobody has answered yet, AGRC-129 takes the passages HU-12 found relevant in the organization's uploaded documents and prepares a **proposal**: a short answer, written as the representative might say it, with a reference to the file and passage it comes from.

A proposal is not an answer. It becomes the representative's statement only when they confirm or correct it (AGRC-130). Until then it is not attributed to them, not used by the agent and not shown in results or reports.

Out of scope here: finding the passages (HU-12), the confirmation screen (AGRC-130) and the end-to-end acceptance tests (AGRC-131).

## 2. Input: a passage match from HU-12

AGRC-129 is built against this contract, so it can be developed and tested with fake matches before HU-12 lands. **To confirm with Mihailo.**

| Field | Type | Notes |
| --- | --- | --- |
| `organization_id` | UUID | Must equal the file's and the control's organization |
| `assessment_id` | UUID | The assessment the control belongs to |
| `assessment_control_id` | UUID | The in-scope control the passage supports |
| `evidence_file_id` | UUID | The uploaded file |
| `locator` | object | Where the passage is: `page`, `section` (optional), `char_start`, `char_end` in `extracted_text` |
| `excerpt` | string, ≤ 300 chars | Literal text, same limit as `EvidenceReference.excerpt` |
| `confidence` | 0–1 | How sure the matcher is that the passage is about this control |
| `matcher_version` | string | So a new matcher run can be told apart from an old one |

## 3. Which controls get a proposal

A control gets a proposal only when **all** of these hold:

1. It is in the assessment scope (`assessment_controls`).
2. It is **unanswered**: it has no `control_results` version, and no participant answer turn exists for a question mapped to it.
3. At least one match for it has `confidence ≥ MIN_MATCH_CONFIDENCE` (proposed 0.6, tuned with the eval set).
4. The matched file belongs to the same organization, and either to the same assessment or to no assessment, the same rule `evidence_control_links` already enforces.

No match above the threshold means **no proposal**: the control stays unanswered. A policy document on its own is never read as proof that a control is implemented (section 5).

## 4. Data model: `evidence_answer_proposals` (new table, migration 0012)

| Column | Notes |
| --- | --- |
| `id`, `organization_id`, `assessment_id`, `assessment_control_id`, `evidence_file_id` | Composite foreign keys with `organization_id`, as in `evidence_control_links`, so a proposal cannot cross organizations |
| `locator` (jsonb), `excerpt` (text, ≤ 300) | Copied from the match: the traceable reference |
| `passage_key` (text) | `sha256(evidence_file_id, char_start, char_end, excerpt)`: identifies the passage |
| `proposed_text` | The proposed answer |
| `match_confidence`, `matcher_version`, `prompt_id`, `prompt_version` | How it was produced |
| `state` | `proposed`, `confirmed`, `corrected`, `rejected`, `superseded` |
| `final_text` | The text the representative confirmed (= `proposed_text`) or wrote (corrected); null otherwise |
| `decided_by_user_id`, `decided_at` | Who decided and when; null while `proposed` |
| `created_at` | |

Constraints:

- `UNIQUE (assessment_control_id, passage_key)`: processing the same evidence again does not create a second proposal (**idempotent**).
- `decided_by_user_id IS NULL` exactly when `state` is `proposed` or `superseded`.
- `final_text` is set exactly when `state` is `confirmed` or `corrected`.
- At most one `confirmed`/`corrected` proposal per control (partial unique index), so a control never gets two document-based answers.

A new `matcher_version` that no longer finds a passage marks its `proposed` rows `superseded`. Decided rows are never changed or deleted: they are part of the record.

## 5. Writing the proposal and keeping documents apart from verified evidence

The proposal is written by the local model with a new prompt (`evidence_answer_proposal` 0.1.0). It gets the question, what we need to learn and the excerpt, and must:

- say only what the excerpt says, phrased as "Our *<file name>* states that …";
- not claim the control is implemented, only that the document describes it;
- return nothing when the excerpt does not answer the question (then no proposal is stored).

If the model is unavailable, a template is used: `Our <file> (p. <page>) states: "<excerpt>"`.

Everything a proposal produces keeps its origin visible:

- its reference is an `EvidenceReference` with `source_type = "document_span"` and `nature = "intent"`: a document says the control exists, which is not the same as an expert verifying it (`implementation`);
- any result built from a confirmed proposal keeps `evidence_pending = true` and `requires_human_review = true`, until a consultant verifies it.

## 6. What happens after the representative decides

| Decision | Effect |
| --- | --- |
| Confirm | `state = confirmed`, `final_text = proposed_text` |
| Correct | `state = corrected`, `final_text` = their text (not blank, ≤ 2000 chars) |
| Reject | `state = rejected`; the control stays unanswered and the same passage is not proposed again |

Only an active **representative** of the organization can decide (`organization_memberships.role = 'representative'`). Consultants and administrators can read proposals but not decide on behalf of the organization.

A confirmed or corrected answer is then interpreted **like an interview answer**: the same `interpret` prompt and the same deterministic rules (`decide_next_step`), with the document reference attached. This reuses the HU-05/06 behaviour: a detailed "yes" still gets an evidence request before it closes, so a policy alone never closes a control as implemented. See decision D2.

## 7. Traceability

| Moment | Decision trace |
| --- | --- |
| Proposal created | `evidence_extracted`: sources = the file and passage; output = proposal id, excerpt, confidence; `evidence_nature = "intent"` |
| Representative decides | `answer_interpreted` once the confirmed text is interpreted; sources include the proposal |

## 8. Open decisions

| # | Question | Proposal |
| --- | --- | --- |
| D1 | Match contract (section 2) | Confirm with Mihailo before HU-12 starts |
| D2 | How a confirmed answer reaches the result: (a) interpret it with the same prompt and rules as an interview answer, or (b) create an agent result version directly | (a): reuses the rules and their tests, and keeps one path to a result |
| D3 | Can a proposal be generated for a control that the interview already started, but has not answered? | No: only fully unanswered controls (section 3), so a proposal never competes with what the participant is saying |
| D4 | Threshold `MIN_MATCH_CONFIDENCE` | 0.6 to start; set it with an eval set of matched and unmatched passages |
| D5 | When are proposals generated: on upload, on demand from the UI, or both | On demand (`POST .../proposals:generate`), idempotent, so the representative chooses when |

## 9. API (for AGRC-130)

| Method and path | Who | Does |
| --- | --- | --- |
| `POST /organizations/{org}/assessments/{a}/answer-proposals:generate` | Representative, consultant | Builds proposals from the current matches; returns the created and existing ones |
| `GET /organizations/{org}/assessments/{a}/answer-proposals` | Members | Lists proposals with their file and passage reference |
| `POST /organizations/{org}/assessments/{a}/answer-proposals/{id}/decision` | Representative | Body: `{"action": "confirm" \| "correct" \| "reject", "text": "..."}` |

## 10. Tests that cover the "Done when" of AGRC-129

| Done when | Test |
| --- | --- |
| A relevant passage gives a proposal with a traceable file and passage reference | Service test with a fake match: the proposal has the file id, locator and excerpt |
| The proposal is identified as document-derived and unverified | Its reference is `document_span` / `intent`; results built from it keep `evidence_pending` and review |
| Nothing is attributed to the representative before they approve | No turn, answer or result exists while `state = proposed`; the agent ignores it |
| Controls without a relevant passage stay unanswered | No match, or a match below the threshold, gives no proposal |
| Evidence from another organization or assessment is rejected | Service check and composite foreign keys; database test |
| Reprocessing does not duplicate | Running generate twice gives the same rows; unique constraint test |
| The backend exposes proposals and sources | API tests for list and decision, including role checks |
