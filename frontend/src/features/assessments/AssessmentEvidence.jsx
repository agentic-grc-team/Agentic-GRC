import { useEffect, useRef, useState } from "react";

import EvidenceUpload from "../organizations/EvidenceUpload.jsx";
import {
  linkEvidence,
  listAssessmentControls,
  listAssessmentEvidence,
  listEvidenceLinks,
  unlinkEvidence,
} from "./api.js";

function describeError(error) {
  if (error?.status === 401) {
    return "Your session has expired. Sign in again to continue.";
  }
  if (error?.status === 404) {
    return "This assessment was not found, or you do not have access to it.";
  }
  if (error?.status === 403) {
    return "You need active membership in this organization to manage evidence.";
  }
  return error?.message || "Something went wrong. Please try again.";
}

// Attach uploaded documents to the controls of an assessment so reviewers can see them (AGRC-81).
export default function AssessmentEvidence({ organizationId, assessmentId, accessToken, sessionId = "" }) {
  const [controls, setControls] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [links, setLinks] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [pending, setPending] = useState("");
  const [choices, setChoices] = useState({});
  const [reload, setReload] = useState(0);
  const accessTokenRef = useRef(accessToken);
  const scopeRef = useRef("");
  const scopeKey = `${organizationId}:${assessmentId}:${sessionId}`;

  useEffect(() => {
    accessTokenRef.current = accessToken;
  }, [accessToken]);

  useEffect(() => {
    scopeRef.current = scopeKey;
  }, [scopeKey]);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setLoadError("");
    setActionError("");
    setChoices({});

    Promise.all([
      listAssessmentControls(organizationId, assessmentId, accessTokenRef.current),
      listAssessmentEvidence(organizationId, assessmentId, accessTokenRef.current),
      listEvidenceLinks(organizationId, assessmentId, accessTokenRef.current),
    ])
      .then(([controlItems, documentItems, linkItems]) => {
        if (!active) return;
        setControls(Array.isArray(controlItems) ? controlItems : []);
        setDocuments(Array.isArray(documentItems) ? documentItems : []);
        setLinks(Array.isArray(linkItems) ? linkItems : []);
      })
      .catch((error) => {
        if (!active) return;
        setControls([]);
        setDocuments([]);
        setLinks([]);
        setLoadError(describeError(error));
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [organizationId, assessmentId, sessionId, reload]);

  const documentsById = new Map(documents.map((document) => [document.id, document]));

  function linkedDocuments(controlId) {
    return links
      .filter((link) => link.assessment_control_id === controlId)
      .map((link) => documentsById.get(link.evidence_file_id))
      .filter(Boolean);
  }

  async function attach(control) {
    const evidenceId = choices[control.id];
    if (!evidenceId || pending) return;
    const scope = scopeRef.current;
    setPending(`attach:${control.id}`);
    setActionError("");
    try {
      const link = await linkEvidence(organizationId, evidenceId, control.id, accessTokenRef.current);
      if (scopeRef.current !== scope) return;
      setLinks((current) => (current.some((item) => item.id === link.id) ? current : [...current, link]));
      setChoices((current) => ({ ...current, [control.id]: "" }));
    } catch (error) {
      if (scopeRef.current !== scope) return;
      setActionError(describeError(error));
    } finally {
      setPending("");
    }
  }

  async function detach(control, document) {
    if (pending) return;
    const scope = scopeRef.current;
    setPending(`detach:${control.id}:${document.id}`);
    setActionError("");
    try {
      await unlinkEvidence(organizationId, document.id, control.id, accessTokenRef.current);
      if (scopeRef.current !== scope) return;
      setLinks((current) =>
        current.filter(
          (link) => !(link.assessment_control_id === control.id && link.evidence_file_id === document.id),
        ),
      );
    } catch (error) {
      if (scopeRef.current !== scope) return;
      setActionError(describeError(error));
    } finally {
      setPending("");
    }
  }

  return (
    <section className="assessment-evidence" aria-labelledby="assessment-evidence-heading">
      <p className="eyebrow">EVIDENCE</p>
      <h2 id="assessment-evidence-heading">Evidence for this assessment</h2>
      <p className="assessment-note">
        Upload documents here and attach them to the controls they support. Reviewers see the attached
        documents next to each control. Attached documents still need consultant verification.
      </p>

      <EvidenceUpload
        organizationId={organizationId}
        assessmentId={assessmentId}
        accessToken={accessToken}
        sessionId={sessionId}
        onUploaded={() => setReload((count) => count + 1)}
      />

      {isLoading && <p role="status">Loading evidence…</p>}
      {loadError && (
        <div>
          <p role="alert">{loadError}</p>
          <button className="secondary-button" type="button" onClick={() => setReload((count) => count + 1)}>
            Retry loading evidence
          </button>
        </div>
      )}
      {actionError && <p role="alert">{actionError}</p>}

      {!isLoading && !loadError && controls.length > 0 && (
        <ul className="assessment-evidence-controls" aria-label="Evidence by control">
          {controls.map((control) => {
            const attached = linkedDocuments(control.id);
            const attachedIds = new Set(attached.map((document) => document.id));
            const available = documents.filter((document) => !attachedIds.has(document.id));
            const selectId = `evidence-choice-${control.id}`;
            return (
              <li key={control.id}>
                <div className="assessment-evidence-heading">
                  <span className="assessment-control-code">{control.code}</span>
                  <span>{control.title}</span>
                </div>

                {attached.length === 0 ? (
                  <p className="assessment-note">No documents attached.</p>
                ) : (
                  <ul aria-label={`Documents attached to ${control.code}`}>
                    {attached.map((document) => (
                      <li key={document.id}>
                        <span>{document.original_filename}</span>
                        <button
                          className="text-button"
                          type="button"
                          disabled={Boolean(pending)}
                          aria-label={`Remove ${document.original_filename} from ${control.code}`}
                          onClick={() => detach(control, document)}
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                {available.length > 0 && (
                  <div className="assessment-evidence-attach">
                    <label htmlFor={selectId}>{`Attach a document to ${control.code}`}</label>
                    <select
                      id={selectId}
                      value={choices[control.id] || ""}
                      onChange={(event) =>
                        setChoices((current) => ({ ...current, [control.id]: event.target.value }))
                      }
                    >
                      <option value="">Choose a document</option>
                      {available.map((document) => (
                        <option key={document.id} value={document.id}>
                          {document.original_filename}
                        </option>
                      ))}
                    </select>
                    <button
                      className="secondary-button"
                      type="button"
                      disabled={!choices[control.id] || Boolean(pending)}
                      aria-label={`Attach to ${control.code}`}
                      onClick={() => attach(control)}
                    >
                      {pending === `attach:${control.id}` ? "Attaching…" : "Attach"}
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {!isLoading && !loadError && documents.length === 0 && controls.length > 0 && (
        <p className="assessment-note">Upload a document above to attach it to a control.</p>
      )}
    </section>
  );
}
