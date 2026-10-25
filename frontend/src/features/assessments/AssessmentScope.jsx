import { assessmentStatusLabel } from "./statusLabels.js";

function formatDate(value) {
  if (!value) {
    return "Not started";
  }
  const date = new Date(value);
  // An unparseable date would make toISOString() throw and break the whole screen.
  return Number.isNaN(date.getTime()) ? "Unknown" : date.toISOString().slice(0, 10);
}

function plural(count, singular, pluralForm) {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

// The NIST CSF 2.0 functions, categories and controls an assessment covers (HU-04, AGRC-63).
export default function AssessmentScope({ scope }) {
  const assessment = scope.assessment;
  const functions = scope.functions || [];
  const categoryCount = functions.reduce((total, item) => total + item.categories.length, 0);

  return (
    <section className="assessment-scope" aria-labelledby="assessment-scope-heading">
      <p className="eyebrow">ASSESSMENT SCOPE</p>
      <h2 id="assessment-scope-heading">{assessment.title}</h2>

      <dl className="assessment-facts">
        <div>
          <dt>Organization</dt>
          <dd>{scope.organization_name}</dd>
        </div>
        <div>
          <dt>Framework</dt>
          <dd>NIST CSF {assessment.framework_version}</dd>
        </div>
        <div>
          <dt>Knowledge base</dt>
          <dd>{assessment.kb_version}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{formatDate(assessment.started_at)}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{assessmentStatusLabel(assessment.status)}</dd>
        </div>
      </dl>

      {functions.length === 0 ? (
        <p role="alert">No controls are in scope for this assessment, so there is nothing to assess yet.</p>
      ) : (
        <>
          <p className="assessment-scope-summary">
            {`${plural(scope.control_count, "control", "controls")} in ${plural(categoryCount, "category", "categories")} and ${plural(functions.length, "function", "functions")}. `}
            The interview only covers these controls.
          </p>

          {functions.map((csfFunction) => (
            <div className="assessment-function" key={csfFunction.code}>
              <h3>{`${csfFunction.name} (${csfFunction.code})`}</h3>
              {csfFunction.categories.map((category) => (
                <div className="assessment-category" key={category.code}>
                  <h4>{category.name ? `${category.code} · ${category.name}` : category.code}</h4>
                  <ul aria-label={`Controls in ${category.code}`}>
                    {category.controls.map((control) => (
                      <li key={control.code}>
                        <span className="assessment-control-code">{control.code}</span>
                        <span>{control.title}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ))}
        </>
      )}
    </section>
  );
}
