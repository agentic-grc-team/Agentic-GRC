import "./ComplianceSummary.css";

const STATUS_LABELS = [
  ["implemented", "Implemented"],
  ["partially_implemented", "Partially implemented"],
  ["not_implemented", "Not implemented"],
  ["not_assessed", "Not assessed"],
];

export default function ComplianceSummary({ summary, assessmentTitle, exclusionCount = 0 }) {
  if (!summary) return null;

  const counts = summary.status_counts || {};
  const compliance = summary.compliance;
  const figure =
    compliance?.available && Number.isFinite(compliance.value_pct)
      ? `${compliance.value_pct.toFixed(1)}%`
      : "Unavailable";
  const coverage = Number.isFinite(summary.coverage_pct)
    ? `${summary.coverage_pct.toFixed(1)}%`
    : "0.0%";

  return (
    <section className="compliance-summary" aria-labelledby="compliance-summary-heading">
      <div className="compliance-summary-header">
        <div>
          <p className="eyebrow">ASSESSMENT PROGRESS</p>
          <h2 id="compliance-summary-heading">Compliance summary</h2>
          {assessmentTitle && (
            <p className="compliance-summary-assessment">Assessment: {assessmentTitle}</p>
          )}
        </div>
        <p className="compliance-summary-figure">
          <strong>{figure}</strong>
          <span>compliance figure</span>
        </p>
      </div>
      <p className="compliance-summary-caption">
        {compliance?.definition || "The compliance figure is not available in this report yet."}
      </p>
      {compliance && (
        <p className="compliance-summary-basis">
          Based on {compliance.denominator} of {summary.controls_in_scope} controls ·{" "}
          {compliance.excluded_not_applicable} not applicable · {compliance.not_assessed} not
          assessed · {compliance.pending} pending
        </p>
      )}
      <dl className="compliance-summary-counts">
        {STATUS_LABELS.map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{counts[key] ?? 0}</dd>
          </div>
        ))}
      </dl>
      <p className="compliance-summary-footnote">
        Review coverage: {coverage} · {summary.pending ?? 0} awaiting a final result ·{" "}
        {exclusionCount} approved exclusions. Review coverage is not a compliance score.
      </p>
    </section>
  );
}
