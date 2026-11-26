import { useEffect, useRef, useState } from "react";

import { getAssessmentComparison, getComparisonCandidates } from "./api.js";
import "./AssessmentComparison.css";

const STATUS_LABELS = {
  implemented: "Implemented",
  partially_implemented: "Partially implemented",
  not_implemented: "Not implemented",
  not_assessed: "Not assessed",
  not_applicable: "Not applicable",
  pending: "Pending review",
};

const CHANGE_LABELS = {
  improved: "Improved",
  declined: "Declined",
  unchanged: "Unchanged",
  not_comparable: "Not comparable",
};

function complianceText(compliance) {
  return compliance?.available && Number.isFinite(compliance.value_pct)
    ? `${compliance.value_pct.toFixed(1)}%`
    : "Unavailable";
}

export default function AssessmentComparison({
  organizationId,
  currentAssessmentId,
  current,
  accessToken,
}) {
  const [candidates, setCandidates] = useState(null);
  const [candidatesError, setCandidatesError] = useState("");
  const [candidatesRetry, setCandidatesRetry] = useState(0);
  const [previousId, setPreviousId] = useState("");
  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const tokenRef = useRef(accessToken);
  tokenRef.current = accessToken;

  useEffect(() => {
    let active = true;
    setCandidates(null);
    setCandidatesError("");
    getComparisonCandidates(organizationId, currentAssessmentId, tokenRef.current)
      .then((data) => {
        if (active) setCandidates(data);
      })
      .catch((failure) => {
        if (active) setCandidatesError(failure?.message || "Could not load earlier assessments.");
      });
    return () => {
      active = false;
    };
  }, [organizationId, currentAssessmentId, candidatesRetry]);

  useEffect(() => {
    let active = true;
    setComparison(null);
    setError("");
    if (!previousId) {
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    getAssessmentComparison(organizationId, currentAssessmentId, previousId, tokenRef.current)
      .then((data) => {
        if (!active) return;
        if (data.current?.id !== currentAssessmentId || data.previous?.id !== previousId) {
          throw new Error("Comparison does not belong to the selected assessments.");
        }
        setComparison(data);
      })
      .catch((failure) => {
        if (active) setError(failure?.message || "Could not load the comparison.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [organizationId, currentAssessmentId, previousId, retry]);

  const visibleComparison =
    comparison?.current?.id === currentAssessmentId && comparison?.previous?.id === previousId
      ? comparison
      : null;

  return (
    <section className="assessment-comparison" aria-labelledby="assessment-comparison-heading">
      <p className="eyebrow">ASSESSMENT HISTORY</p>
      <h3 id="assessment-comparison-heading">Compare with a previous assessment</h3>
      {current.assessment.status !== "completed" && (
        <p className="assessment-comparison-note">
          This assessment is not completed yet. Its results and compliance figure can still change.
        </p>
      )}
      {candidates === null && !candidatesError && <p role="status">Loading earlier assessments…</p>}
      {candidatesError && (
        <div role="alert" className="report-error-message">
          <span>{candidatesError}</span>
          <button
            type="button"
            className="text-button"
            onClick={() => setCandidatesRetry((count) => count + 1)}
          >
            Try again
          </button>
        </div>
      )}
      {candidates?.length === 0 && (
        <p>No earlier completed assessments are available for this organization.</p>
      )}
      {candidates?.length > 0 && (
        <>
          <label className="report-org-select">
            Previous assessment
            <select value={previousId} onChange={(event) => setPreviousId(event.target.value)}>
              <option value="" disabled>
                Select an assessment
              </option>
              {candidates.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          {loading && <p role="status">Loading comparison…</p>}
          {error && (
            <div role="alert" className="report-error-message">
              <span>{error}</span>
              <button
                type="button"
                className="text-button"
                onClick={() => setRetry((count) => count + 1)}
              >
                Try again
              </button>
            </div>
          )}
          {visibleComparison && !loading && !error && (
            <>
              {visibleComparison.warnings.map((warning) => (
                <p key={warning.code} className="assessment-comparison-warning" role="note">
                  {warning.message}
                </p>
              ))}
              <p className="assessment-comparison-note">
                Compliance: {complianceText(visibleComparison.previous.compliance)} previously →{" "}
                {complianceText(visibleComparison.current.compliance)} now.
                {visibleComparison.compliance_change_pct !== null && (
                  <>
                    {" "}
                    Change: {visibleComparison.compliance_change_pct > 0 ? "+" : ""}
                    {visibleComparison.compliance_change_pct.toFixed(1)} percentage points.
                  </>
                )}
              </p>
              <p className="assessment-comparison-note">
                {visibleComparison.scope.common} shared controls ·{" "}
                {visibleComparison.scope.added.length} new in this scope ·{" "}
                {visibleComparison.scope.removed.length} only in the previous scope
              </p>
              {visibleComparison.controls.length === 0 ? (
                <p>No controls are shared by these assessments.</p>
              ) : (
                <div className="assessment-comparison-table-wrap">
                  <table aria-label="Control status comparison">
                    <thead>
                      <tr>
                        <th scope="col">Control</th>
                        <th scope="col">Previous</th>
                        <th scope="col">Current</th>
                        <th scope="col">Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleComparison.controls.map((row) => (
                        <tr key={row.code}>
                          <th scope="row">
                            <strong>{row.code}</strong>
                            <span>{row.title}</span>
                          </th>
                          <td>{STATUS_LABELS[row.previous_status] || row.previous_status}</td>
                          <td>{STATUS_LABELS[row.current_status] || row.current_status}</td>
                          <td>{CHANGE_LABELS[row.change] || row.change}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
