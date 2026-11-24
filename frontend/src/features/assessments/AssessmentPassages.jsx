import { useEffect, useRef, useState } from "react";

import { getPassageMatches } from "./api.js";
import "./AssessmentPassages.css";

export default function AssessmentPassages({ scope, organizationId, assessmentId, accessToken }) {
  const controls = (scope.functions || []).flatMap((group) =>
    group.categories.flatMap((category) => category.controls),
  );
  const [selectedCode, setSelectedCode] = useState(controls[0]?.code || "");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef(0);
  const tokenRef = useRef(accessToken);
  tokenRef.current = accessToken;

  useEffect(() => () => {
    requestRef.current += 1;
  }, []);

  async function loadMatches() {
    const request = ++requestRef.current;
    setLoading(true);
    setError("");
    try {
      const data = await getPassageMatches(organizationId, assessmentId, tokenRef.current);
      if (request === requestRef.current) setResult(data);
    } catch (failure) {
      if (request === requestRef.current) setError(failure?.message || "Could not load passage matches.");
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  }

  if (controls.length === 0) return null;

  const matches = (result?.matches || []).filter((item) => item.control_code === selectedCode);
  const noTerms = result?.controls_without_terms?.includes(selectedCode);
  const documentCount = new Set(matches.map((match) => match.evidence_file_id)).size;

  return (
    <section className="assessment-passages" aria-labelledby="assessment-passages-heading">
      <p className="eyebrow">DOCUMENT MATCHES</p>
      <h2 id="assessment-passages-heading">Passages relevant to controls</h2>
      <p className="assessment-note">
        These are suggested matches, not verified evidence or confirmed answers.
        Finding a passage does not attach the file or change a control result.
      </p>

      <label className="assessment-field">
        Control
        <select value={selectedCode} onChange={(event) => setSelectedCode(event.target.value)}>
          {controls.map((control) => (
            <option key={control.code} value={control.code}>
              {`${control.code} · ${control.title}`}
            </option>
          ))}
        </select>
      </label>
      <button className="secondary-button" type="button" disabled={loading} onClick={loadMatches}>
        {loading ? "Finding passages…" : result ? "Refresh matches" : "Find relevant passages"}
      </button>

      {loading && <p role="status">Checking uploaded documents…</p>}
      {error && <p role="alert">{error}</p>}
      {result && !loading && (
        <div className="assessment-passages-results">
          {matches.length > 0 && (
            <p className="assessment-note">
              {`${matches.length} matching ${matches.length === 1 ? "passage" : "passages"} from ${documentCount} ${documentCount === 1 ? "document" : "documents"}.`}
            </p>
          )}
          {noTerms ? (
            <p className="assessment-note">
              Matching terms are not available for this control yet; no conclusion can be drawn.
            </p>
          ) : result.files_checked === 0 ? (
            <p className="assessment-note">No uploaded documents are available to check.</p>
          ) : matches.length === 0 ? (
            <p className="assessment-note">
              {`No matching passages found in ${result.files_checked} ${result.files_checked === 1 ? "document" : "documents"} checked.`}
            </p>
          ) : (
            <ul aria-label={`Passages for ${selectedCode}`}>
              {matches.map((match) => (
                <li key={`${match.evidence_file_id}:${match.locator.char_start}:${match.control_code}`}>
                  <strong>{match.file_name}</strong>
                  <p className="assessment-passages-location">
                    {[
                      match.locator.page && `Page ${match.locator.page}`,
                      match.locator.section && `Section ${match.locator.section}`,
                      `Characters ${match.locator.char_start}–${match.locator.char_end}`,
                    ].filter(Boolean).join(" · ")}
                  </p>
                  <blockquote>{match.excerpt}</blockquote>
                  <p className="assessment-passages-location">
                    {`Source: ${match.reference} · Matched: ${match.matched_terms.join(", ")} · Match score: ${match.confidence}`}
                  </p>
                  <p className="assessment-passages-location">
                    {match.linked ? "File already linked to this control" : "File not linked to this control"}
                  </p>
                </li>
              ))}
            </ul>
          )}
          <p className="assessment-passages-footnote">
            {`Matcher: ${result.matcher_version}. The match score ranks passages; it is not a probability that a control is implemented.`}
          </p>
        </div>
      )}
    </section>
  );
}