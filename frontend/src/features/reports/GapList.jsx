import { useEffect, useRef, useState } from "react";

import { getGapList } from "./api.js";
import "./GapList.css";

const BASIS_LABELS = {
  accepted_agent_result: "accepted agent result",
  consultant_version: "consultant version",
};

function describeGapError(error) {
  if (error?.status === 401) {
    return "Your session has expired. Sign in again to continue.";
  }
  return error?.message || "The gaps could not be loaded.";
}

// HU-17: the gaps of an assessment, ordered by criticality, so the security officer knows where to start.
export default function GapList({ organizationId, assessmentId, accessToken }) {
  const [gapList, setGapList] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [retryCounter, setRetryCounter] = useState(0);
  // Like the report, a refreshed token alone does not reload the list; the latest token is used for each request.
  const tokenRef = useRef(accessToken);

  useEffect(() => {
    tokenRef.current = accessToken;
  }, [accessToken]);

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    setError(null);
    getGapList(organizationId, assessmentId, tokenRef.current)
      .then((data) => {
        if (isCurrent) setGapList(data);
      })
      .catch((caught) => {
        if (isCurrent) setError(caught);
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });
    return () => {
      isCurrent = false;
    };
  }, [organizationId, assessmentId, retryCounter]);

  return (
    <div className="report-section gap-list">
      <h3>Gaps by criticality</h3>

      {isLoading && <p className="gap-list-loading">Loading gaps…</p>}

      {!isLoading && error && (
        <div role="alert" className="report-error-message gap-list-error">
          <span>{describeGapError(error)}</span>
          <button className="text-button" type="button" onClick={() => setRetryCounter((count) => count + 1)}>
            Try again
          </button>
        </div>
      )}

      {!isLoading && !error && gapList && (
        <>
          <p className="gap-list-intro">
            Controls whose reviewed result is partially or not implemented, most critical first: by priority, then
            by the most severe risk, then not implemented before partially implemented.
          </p>
          {gapList.rules_provisional && (
            <p className="gap-list-provisional">
              {`Priorities and risks follow Aligo's classification guide and are provisional until Aligo confirms them (rules ${gapList.rules_version}).`}
            </p>
          )}
          {gapList.pending_controls > 0 && (
            <p className="gap-list-pending">
              {`${gapList.pending_controls} control(s) still pending expert review are not included.`}
            </p>
          )}

          {gapList.gaps.length === 0 ? (
            <p>No gaps among the reviewed results.</p>
          ) : (
            <div className="report-table-wrap">
              <table className="report-table" aria-label="Gaps by criticality">
                <thead>
                  <tr>
                    <th scope="col">#</th>
                    <th scope="col">Control</th>
                    <th scope="col">Status</th>
                    <th scope="col">Priority</th>
                    <th scope="col">Risks</th>
                    <th scope="col">Why</th>
                  </tr>
                </thead>
                <tbody>
                  {gapList.gaps.map((gap, index) => (
                    <tr key={gap.control_code}>
                      <td>{index + 1}</td>
                      <td>
                        <strong>{gap.control_code}</strong>
                        <span className="gap-list-title">{gap.control_title}</span>
                      </td>
                      <td>
                        <span className={`report-status report-status--${gap.control_status}`}>{gap.status_label}</span>
                        <span className="gap-list-basis">
                          {`Based on version ${gap.result_version} · ${BASIS_LABELS[gap.basis] || gap.basis}`}
                        </span>
                      </td>
                      <td>
                        {gap.classified ? (
                          <span className={`gap-priority gap-priority--${gap.priority.toLowerCase()}`}>
                            {gap.priority}
                          </span>
                        ) : (
                          <span className="gap-priority gap-priority--none">Not classified</span>
                        )}
                      </td>
                      <td>
                        {gap.risks.length === 0 ? (
                          "—"
                        ) : (
                          <ul className="gap-risks">
                            {gap.risks.map((risk) => (
                              <li key={risk.name}>{`${risk.name} (${risk.severity})`}</li>
                            ))}
                          </ul>
                        )}
                      </td>
                      <td>{gap.classified ? gap.reason : "No classification rule for this control yet."}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
