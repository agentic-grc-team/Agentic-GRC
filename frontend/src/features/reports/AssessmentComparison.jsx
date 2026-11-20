import { useEffect, useRef, useState } from "react";

import { getReportPreview } from "./api.js";
import "./AssessmentComparison.css";

const RANK = { not_implemented: 0, partially_implemented: 1, implemented: 2 };

function finalState(report, code) {
  const result = report.results?.find((item) => item.code === code);
  if (result) return { label: result.status_label, status: result.control_status };
  if (report.exclusions?.some((item) => item.code === code)) return { label: "Excluded", status: "excluded" };
  const pending = report.pending?.find((item) => item.code === code);
  return { label: pending?.reason_label || "No final result", status: null };
}

function movement(before, after) {
  if (!Object.hasOwn(RANK, before) || !Object.hasOwn(RANK, after)) return "Not comparable";
  if (RANK[after] > RANK[before]) return "Improved";
  if (RANK[after] < RANK[before]) return "Declined";
  return "Unchanged";
}

function compareReports(previous, current) {
  const oldScope = new Set((previous.scope || []).map((item) => item.code));
  const newScope = new Set((current.scope || []).map((item) => item.code));
  const rows = (current.scope || []).filter((item) => oldScope.has(item.code)).map((item) => {
    const before = finalState(previous, item.code);
    const after = finalState(current, item.code);
    return { ...item, before: before.label, after: after.label, change: movement(before.status, after.status) };
  });
  return {
    rows,
    added: [...newScope].filter((code) => !oldScope.has(code)).length,
    removed: [...oldScope].filter((code) => !newScope.has(code)).length,
  };
}

export default function AssessmentComparison({ organizationId, currentAssessmentId, assessments, current, accessToken }) {
  const [previousId, setPreviousId] = useState("");
  const [previous, setPrevious] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const tokenRef = useRef(accessToken);
  tokenRef.current = accessToken;

  const selected = assessments.find((item) => item.id === currentAssessmentId);
  const selectedTime = Date.parse(selected?.created_at || "");
  const candidates = Number.isFinite(selectedTime)
    ? assessments.filter((item) => item.id !== currentAssessmentId && Number.isFinite(Date.parse(item.created_at)) && Date.parse(item.created_at) < selectedTime)
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    : [];

  useEffect(() => {
    let active = true;
    setPrevious(null);
    setError("");
    if (!previousId) {
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    getReportPreview(organizationId, previousId, tokenRef.current)
      .then((data) => { if (active) setPrevious(data); })
      .catch(() => { if (active) setError("Could not load the previous assessment."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [organizationId, previousId, retry]);

  const comparison = previous ? compareReports(previous, current) : null;

  return (
    <section className="assessment-comparison" aria-labelledby="assessment-comparison-heading">
      <p className="eyebrow">ASSESSMENT HISTORY</p>
      <h3 id="assessment-comparison-heading">Compare with a previous assessment</h3>
      {candidates.length === 0 ? (
        <p>No earlier assessments are available for this organization.</p>
      ) : (
        <>
          <label className="report-org-select">
            Previous assessment
            <select value={previousId} onChange={(event) => setPreviousId(event.target.value)}>
              <option value="" disabled>Select an assessment</option>
              {candidates.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
            </select>
          </label>
          {loading && <p role="status">Loading comparison…</p>}
          {error && (
            <div role="alert" className="report-error-message">
              <span>{error}</span>
              <button type="button" className="text-button" onClick={() => setRetry((count) => count + 1)}>Try again</button>
            </div>
          )}
          {comparison && !loading && !error && (
            <>
              <p className="assessment-comparison-note">
                Review coverage: {previous.summary.coverage_pct.toFixed(1)}% previously → {current.summary.coverage_pct.toFixed(1)}% now.
                Coverage measures finalized controls, not compliance. Only controls in both assessments are compared.
              </p>
              <p className="assessment-comparison-note">
                {comparison.rows.length} shared controls · {comparison.added} new in this scope · {comparison.removed} only in the previous scope
              </p>
              {comparison.rows.length === 0 ? <p>No controls are shared by these assessments.</p> : (
                <div className="assessment-comparison-table-wrap">
                  <table aria-label="Control status comparison">
                    <thead><tr><th scope="col">Control</th><th scope="col">Previous</th><th scope="col">Current</th><th scope="col">Change</th></tr></thead>
                    <tbody>{comparison.rows.map((row) => (
                      <tr key={row.code}>
                        <th scope="row"><strong>{row.code}</strong><span>{row.title}</span></th>
                        <td>{row.before}</td><td>{row.after}</td><td>{row.change}</td>
                      </tr>
                    ))}</tbody>
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
