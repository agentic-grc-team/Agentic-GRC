# Framework Scope Decision Record

## 1. Document information

| Field | Value |
| --- | --- |
| ID | E0-01 (Jira: AGRC-8) |
| Date | 2026-09-29 |
| Author | Abedin Orahovac |
| Status | Accepted (confirmed with the client on 2026-09-24) |

## 2. Context

The project brief left the choice of cybersecurity framework open between ISO 27001 and NIST CSF. This decision blocks the rest of the product: the controls knowledge base (E0-03) cannot be populated without it, and every interview, evidence and gap-analysis story depends on the knowledge base. The framework was agreed with Aligo Defensores Informáticos in the first client meeting on 2026-09-24.

## 3. Decision

**NIST Cybersecurity Framework (CSF) 2.0**, published by NIST in February 2024, is the fixed framework for the MVP. ISO 27001 remains a possible future alternative and is not part of the MVP. The knowledge base data model (E0-02) treats the framework as an attribute, so a second framework can be added later without changing the architecture.

## 4. Scope: functions and coverage

NIST CSF 2.0 is organized into 6 functions, 22 categories and 106 subcategories. Each subcategory is treated as one control that the agent assesses.

| Function | ID | In scope |
| --- | --- | --- |
| Govern | GV | Yes |
| Identify | ID | Yes |
| Protect | PR | Yes |
| Detect | DE | Yes |
| Respond | RS | Yes |
| Recover | RC | Yes |

All functions and all subcategories are in scope. No NIST domain is excluded at present.

## 5. Rationale

- The client selected NIST CSF 2.0 in the meeting on 2026-09-24.
- The client already works with a NIST CSF 2.0 Maturity Assessment Template and demonstrated its current assessment workflow in Cynomi, so the prototype fits an existing process.
- NIST CSF 2.0 is publicly available, which allows the team to build and test the knowledge base without licensing restrictions.
- The estimate for E0-03 (8 points) assumes NIST CSF 2.0; ISO 27001:2022 Annex A would raise it to 13 points.

## 6. Consequences

- E0-03 (populate the knowledge base) is unblocked.
- Until the client's maturity template and examples arrive, the knowledge base uses a **versioned provisional dataset** built from the public NIST CSF 2.0 documentation. When the client materials arrive, the dataset is updated and released as a new knowledge-base version.
- Questions, evaluation criteria and expected evidence types are defined per NIST CSF 2.0 subcategory.
- Reports and the JSON export reference NIST CSF 2.0 identifiers.
- The first version of the interview and reports is in English; Spanish localization will be considered after the main workflow works.

### Scope change policy

Any later reduction of scope (for example, excluding a function or subcategory) must be recorded as a new entry in the decision log (`docs/decisions/`) and reflected in a new knowledge-base version.

## 7. Out of scope

For the MVP, the following are out of scope:

- ISO 27001 or any second framework
- A full compliance dashboard (Cynomi already covers visualization)
- Direct API integration with Cynomi (the exchange is a JSON file)
- Certification or audit sign-off
- Automatic remediation or continuous monitoring
- Processing real client data (testing uses synthetic or anonymized documents)

## 8. Pending client inputs

Requested from Aligo in the 2026-09-24 meeting and the follow-up email. None has a committed delivery date.

| Input | Needed for | Status |
| --- | --- | --- |
| NIST CSF 2.0 Maturity Assessment Template | Replacing the provisional dataset (E0-03) | Pending |
| Assessment process flowchart | Interview design (E2) | Pending |
| Sample assessment reports | PDF report (HU-20) | Pending |
| Sample policy documents | Evidence mapping (HU-12) | Pending |
| Examples of sufficient and insufficient evidence | Evaluation criteria (E0-03, HU-12) | Pending |

## 9. Client confirmation

| Field | Value |
| --- | --- |
| Confirmed by | Aligo Defensores Informáticos |
| Date | 2026-09-24 (first client meeting) |
| Comments | Written confirmation to be added when the client replies to the follow-up email |