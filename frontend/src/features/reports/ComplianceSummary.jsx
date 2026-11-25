import "./ComplianceSummary.css";

const STATUS_LABELS = [
  ["implemented", "Implemented"],
  ["partially_implemented", "Partially implemented"],
  ["not_implemented", "Not implemented"],
  ["not_assessed", "Not assessed"],
];

export default function ComplianceSummary({ summary, exclusionCount = 0 }) {
  if (!summary) return null;

  const counts = summary.status_counts || {};
  const coverage = Number.isFinite(summary.coverage_pct)
    ? `${summary.coverage_pct.toFixed(1)}%`
    : "0.0%";

  return (
    <section className="compliance-summary" aria-labelledby="compliance-summary-heading">
      <div className="compliance-summary-header">
        <div>
          <p className="eyebrow">ASSESSMENT PROGRESS</p>
          <h2 id="compliance-summary-heading">Compliance summary</h2>
        </div>
        <p className="compliance-summary-coverage">
          <strong>{coverage}</strong>
          <span>review coverage</span>
        </p>
      </div>
      <p className="compliance-summary-caption">
        Review coverage is the share of controls with a final result or approved exclusion. It is
        not a compliance score.
      </p>
      <dl className="compliance-summary-counts">
        {STATUS_LABELS.map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{counts[key] ?? 0}</dd>
          </div>
        ))}
      </dl>
      <p className="compliance-summary-footnote">
        {summary.pending ?? 0} awaiting a final result · {exclusionCount} approved exclusions
      </p>
    </section>
  );
}
