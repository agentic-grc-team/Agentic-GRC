# Framework Scope Decision Record

## 1. Document information

| Field | Value |
| --- | --- |
| ID | E0-01 (Jira: AGRC-8) |
| Date | 2026-09-30 |
| Author | Abedin Orahovac |
| Status | Accepted (confirmed with the client on 2026-09-24 and in writing on 2026-09-30) |

## 2. Context

The project brief left the choice of cybersecurity framework open between ISO 27001 and NIST CSF. This decision blocks the rest of the product: the controls knowledge base (E0-03) cannot be populated without it, and every interview, evidence and gap-analysis story depends on the knowledge base. The framework was agreed with Aligo Defensores Informáticos in the first client meeting on 2026-09-24. Aligo clarified the scope in a written reply to the team's follow-up email and in the handover materials (`00_INDEX.md`).

## 3. Decision

**NIST Cybersecurity Framework (CSF) 2.0** is the fixed framework for the MVP. ISO 27001 remains a possible future alternative and is not part of the MVP. The knowledge base data model (E0-02) treats the framework as an attribute, so a second framework can be added later without changing the architecture.

NIST CSF 2.0 is the **reporting axis, not the interview axis**. Aligo's assessments are organized into 36 topical modules (for example Access, Active Directory, Cloud Security, Email and Messages, Incident Response). Answers and evidence are mapped to CSF 2.0 subcategories afterwards, for the report and the gap analysis. The mapping is **many-to-many**: one answer can provide evidence for several subcategories, and every mapping must carry its own justification.

## 4. Scope: knowledge base and assessment flow

The scope distinguishes between what is **loaded** and what is **assessed**:

| Layer | Scope |
| --- | --- |
| Knowledge base | All 106 NIST CSF 2.0 subcategories, with subcategory text, implementation examples and informative references |
| Assessment flow | 20 to 25 subcategories, covering all six functions, assessed with three evidence sources: interview, documents and Microsoft 365 configuration |

**Source and count:** the knowledge base is built from NIST's official CSF 2.0 Reference Tool export (Excel/JSON). The CSF 2.0 Core has **106 subcategories**: GV 31, ID 21, PR 22, DE 11, RS 13, RC 8. A third-party maturity workbook with 119 rows is **not** used, because 13 of its rows are not part of CSF 2.0 (PR.IP-10 to PR.IP-12 from CSF 1.1, and EX.* extension rows).

The assessment flow focuses on categories where Microsoft 365 configuration and document ingestion can produce evidence:

| Function | Focus category |
| --- | --- |
| Govern (GV) | GV.PO: Policy |
| Identify (ID) | ID.AM: Asset Management |
| Protect (PR) | PR.AA: Identity Management, Authentication and Access Control |
| Protect (PR) | PR.DS: Data Security |
| Detect (DE) | DE.CM: Continuous Monitoring |
| Respond (RS) | RS.MA: Incident Management |
| Recover (RC) | To be selected with Aligo |

The specific subcategories will be selected together with Aligo. No function is excluded from the knowledge base.

## 5. Rationale

- The client selected NIST CSF 2.0 in the meeting on 2026-09-24 and confirmed it in writing.
- The client already maps its findings to CSF 2.0 subcategories. In its current exports this mapping is populated for only a minority of findings, so automating it with justifications is a concrete place where the agent adds value.
- Loading the full framework costs little, so the architecture never limits coverage.
- Depth on 20 to 25 subcategories using three evidence sources demonstrates more than shallow coverage of all 106 through conversation alone.
- NIST CSF 2.0 is publicly available, so the team can build and test without licensing restrictions.

## 6. Consequences

- E0-03 (populate the knowledge base) is unblocked and uses the NIST CSF 2.0 Reference Tool export as its source.
- The data model needs a many-to-many mapping between questions or evidence and CSF 2.0 subcategories, each mapping with a justification and a confidence value.
- The team authors its own question set for the in-scope subcategories, derived from CSF 2.0 subcategories and their implementation examples. Aligo's licensed questionnaire library is not reused.
- Evidence comes from interview answers, uploaded documents, and configuration from a Microsoft 365 / Entra ID test tenant provided by Aligo.
- Control status (Implemented / Partially / Not Implemented), maturity level (1 Performed to 5 Optimizing, an industry convention, not defined by NIST) and remediation task status are separate scales and are stored separately.
- Reports and the JSON export reference NIST CSF 2.0 identifiers.
- The user interface is in English. Document ingestion and part of the test corpus must support Spanish from course Sprint 2.

### Scope change policy

Any later change of scope (for example, adding or removing a subcategory from the assessment flow) must be recorded as a new entry in the decision log (`docs/decisions/`) and reflected in a new knowledge-base version.

## 7. Out of scope

For the MVP, the following are out of scope:

- ISO 27001 or any second framework
- Google Workspace integration (documented as the second integration)
- Access to any live corporate tenant (only Aligo's test tenant is used)
- Reuse of Aligo's licensed questionnaire library
- A full compliance dashboard (Cynomi already covers visualization)
- Direct API integration with Cynomi (the exchange is a JSON file)
- Certification or audit sign-off
- Automatic remediation or continuous monitoring
- Processing real client data (testing uses the fictional Halverston Community Bank scenario and public documents)

## 8. Client inputs

| Input | Needed for | Status |
| --- | --- | --- |
| Handover materials (`00_INDEX.md`): framework source guidance, assessment process, report examples, NIST SP 1353 document corpus, evidence rubric, classification guide, finding data model and draft export schema | Knowledge base, evidence mapping, gap analysis, export, evaluation | Received |
| Microsoft 365 test tenant (Halverston Community Bank scenario) | Configuration evidence | Pending, Aligo is setting it up |
| Selection of the 20 to 25 subcategories for the assessment flow | Scope (section 4) | Pending, to be agreed with Aligo |
| Discrepancies to seed in the test tenant | Evaluation of contradiction detection | Pending, team to propose |

## 9. Client confirmation

| Field | Value |
| --- | --- |
| Confirmed by | Aligo Defensores Informáticos |
| Date | 2026-09-24 (first client meeting), confirmed in writing on 2026-09-30 |
| Comments | Full framework in the knowledge base; 20 to 25 subcategories in the assessment flow; Microsoft 365 as the first integration |