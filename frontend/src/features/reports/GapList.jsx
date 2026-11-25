import "./GapList.css";

const BASIS_LABELS = {
  accepted_agent_result: "accepted agent result",
  consultant_version: "consultant version",
};

// HU-16: each finding shows the evidence behind its result, or says plainly that there is none.
// Like the report, a linked file shows its verification label and whether it was added after the review:
// such a file did not support the reviewed result, so the backend does not count it as evidence.
function GapEvidence({ gap }) {
  const linked = gap.linked_evidence || [];
  const cited = gap.evidence || [];
  if (linked.length === 0 && cited.length === 0) {
    return <span className="gap-evidence-none">No evidence</span>;
  }
  return (
    <>
      {gap.evidence_absent && <span className="gap-evidence-none">No evidence at the time of the review</span>}
      <ul className="gap-evidence">
        {linked.map((file) => (
          <li key={file.id}>
            <span className="gap-evidence-name">{file.file_name}</span>
            <span className="gap-evidence-meta">
              {`${file.file_type} · ${file.verification_label}`}
              {file.added_after_review && " · Added after the review"}
            </span>
          </li>
        ))}
        {cited.map((reference) => (
          <li key={`${reference.source_type}:${reference.reference}`}>{reference.reference}</li>
        ))}
      </ul>
    </>
  );
}

// HU-17: the gaps of an assessment, ordered by criticality, so the security officer knows where to start.
// The list comes with the report preview and is built from the same report view, so the two always agree.
export default function GapList({ gapList }) {
  if (!gapList) return null;

  return (
    <div className="report-section gap-list">
      <h3>Gaps by criticality</h3>

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
          {`${gapList.pending_controls} control(s) without a final reviewed result yet are not included.`}
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
                <th scope="col">Evidence</th>
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
                  <td>
                    <GapEvidence gap={gap} />
                  </td>
                  <td>{gap.classified ? gap.reason : "No classification rule for this control yet."}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
