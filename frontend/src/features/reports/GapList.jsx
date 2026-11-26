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
      {gap.evidence_absent && (
        <span className="gap-evidence-none">No evidence at the time of the review</span>
      )}
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

// HU-18: what to do about the gap and why. A gap without a classification or without a template for its
// control gets no recommendation, rather than an invented one.
function GapRemediation({ gap }) {
  const remediation = gap.remediation;
  if (!remediation) {
    return (
      <p className="gap-remediation-none">
        {gap.classified
          ? "No remediation recommendation for this control yet."
          : "No remediation recommendation without a classification."}
      </p>
    );
  }
  return (
    <details className="gap-remediation">
      <summary>
        {`Recommendation: ${remediation.task}`}
        <span className="gap-remediation-meta">{`${remediation.time_horizon} · ${remediation.dependency}`}</span>
      </summary>
      <dl>
        <dt>Issue</dt>
        <dd>{remediation.issue}</dd>
        <dt>Target state</dt>
        <dd>{remediation.requirement}</dd>
        <dt>What to do</dt>
        <dd>{remediation.task_description}</dd>
      </dl>
      <ol aria-label={`Steps for ${gap.control_code}`}>
        {remediation.how_to.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <p className="gap-remediation-evidence">{`Evidence that closes the gap: ${remediation.evidence_to_close.join("; ")}`}</p>
      <p className="gap-remediation-why">{`Why: ${remediation.justification}`}</p>
    </details>
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
        Controls whose reviewed result is partially or not implemented, most critical first: by
        priority, then by the most severe risk, then not implemented before partially implemented.
      </p>
      {gapList.rules_provisional && (
        <p className="gap-list-provisional">
          {`Priorities and risks follow Aligo's classification guide and are provisional until Aligo confirms them (rules ${gapList.rules_version}).`}
        </p>
      )}
      {gapList.remediation_rules_provisional && gapList.gaps.length > 0 && (
        <p className="gap-list-provisional">
          {`Remediation recommendations are provisional templates until Aligo confirms them (${gapList.remediation_rules_version}), and every recommendation is preliminary until a consultant reviews it.`}
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
                    <span className={`report-status report-status--${gap.control_status}`}>
                      {gap.status_label}
                    </span>
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
                  <td>
                    {gap.classified ? gap.reason : "No classification rule for this control yet."}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {gapList.gaps.length > 0 && (
        <div className="gap-remediation-plan">
          <h4>Remediation recommendations</h4>
          <ol aria-label="Remediation recommendations">
            {gapList.gaps.map((gap) => (
              <li key={gap.control_code}>
                <strong>{gap.control_code}</strong>
                <GapRemediation gap={gap} />
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
