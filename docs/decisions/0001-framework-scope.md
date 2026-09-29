# Framework Scope Decision Record

## 1. Document information

| Field | Value |
| --- | --- |
| ID | E0-01 (Jira: AGRC-8) |
| Date | 2026-09-29 |
| Author | Abedin Orahovac |
| Status | Proposed, awaiting client confirmation |

## 2. Context

The project brief left the choice of cybersecurity framework open between ISO 27001 and NIST CSF. This decision blocks the rest of the product: the controls knowledge base (E0-03) cannot be populated without it, and every interview, evidence and gap-analysis story depends on the knowledge base. The framework was discussed with Aligo Defensores Informáticos in the first client meeting on 2026-09-24.

## 3. Decision

The prototype will use **NIST Cybersecurity Framework (CSF) 2.0**, published by NIST in February 2024, as its initial framework. ISO 27001 is not rejected: it remains a possible second framework after the main workflow works. The knowledge base data model (E0-02) treats the framework as an attribute, so a second framework can be added without changing the architecture.

## 4. Scope: functions and coverage

NIST CSF 2.0 is organized into 6 functions, 22 categories and 106 subcategories. Each subcategory is treated as one control that the agent assesses.

| Function | ID | In knowledge base | In first end-to-end slice |
| --- | --- | --- | --- |
| Govern | GV | Yes | [TBD] |
| Identify | ID | Yes | [TBD] |
| Protect | PR | Yes | [TBD] |
| Detect | DE | Yes | [TBD] |
| Respond | RS | Yes | [TBD] |
| Recover | RC | Yes | [TBD] |

All six functions will be loaded into the knowledge base. The first end-to-end slice (required by the end of course Sprint 6) will cover one function, to be agreed with the client. The level of coverage the client expects for the final prototype is not yet confirmed (see section 8).

## 5. Rationale

- The client selected NIST CSF 2.0 as the starting point in the meeting on 2026-09-24.
- The client already works with a NIST CSF 2.0 Maturity Assessment Template and demonstrated its current assessment workflow in Cynomi, so the prototype fits an existing process.
- NIST CSF 2.0 is publicly available, which allows the team to build and test the knowledge base without licensing restrictions.
- The estimate for E0-03 (8 points) assumes NIST CSF 2.0; ISO 27001:2022 Annex A would raise it to 13 points.

## 6. Consequences

- E0-03 (populate the knowledge base) is unblocked.
- Questions, evaluation criteria and expected evidence types will be defined per NIST CSF 2.0 subcategory.
- Reports and the JSON export will reference NIST CSF 2.0 identifiers (for example, PR.AA-01).
- The first version of the interview and reports will be in English; Spanish localization will be considered after the main workflow works.

## 7. Out of scope

For the prototype, the following are out of scope:

- A second framework (ISO 27001) in this phase
- A full compliance dashboard (Cynomi already covers visualization)
- Direct API integration with Cynomi (the exchange is a JSON file)
- Certification or audit sign-off
- Automatic remediation or continuous monitoring
- Processing real client data (testing uses synthetic or anonymized documents)

## 8. Pending client inputs

Requested from Aligo in the 2026-09-24 meeting and the follow-up email:

| Input | Needed for | Status |
| --- | --- | --- |
| NIST CSF 2.0 Maturity Assessment Template | E0-03 knowledge base | Pending |
| Assessment process flowchart | Interview design (E2) | Pending |
| Sample assessment reports | PDF report (HU-20) | Pending |
| Sample policy documents | Evidence mapping (HU-12) | Pending |
| Examples of sufficient and insufficient evidence | Evaluation criteria (E0-03, HU-12) | Pending |
| Required NIST CSF 2.0 coverage for the prototype | Scope (section 4) | Pending |
| Function for the first end-to-end slice | Scope (section 4) | Pending |

## 9. Client confirmation

| Field | Value |
| --- | --- |
| Confirmed by | |
| Date | |
| Comments | |