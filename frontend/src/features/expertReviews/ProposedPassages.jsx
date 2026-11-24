import { useEffect, useRef, useState } from "react";

import { getPassageMatches } from "../assessments/api.js";
import "./ProposedPassages.css";

export default function ProposedPassages({ organizationId, assessmentId, controlCode, accessToken, sessionId }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef(0);
  const tokenRef = useRef(accessToken);
  tokenRef.current = accessToken;

  useEffect(() => () => {
    requestRef.current += 1;
  }, [organizationId, assessmentId, controlCode, sessionId]);

  async function loadMatches() {
    const request = ++requestRef.current;
    setLoading(true);
    setError("");
    try {
      const data = await getPassageMatches(organizationId, assessmentId, tokenRef.current);
      if (data.organization_id !== organizationId || data.assessment_id !== assessmentId) {
        throw new Error("Passage matches do not belong to this assessment.");
      }
      if (request === requestRef.current) setResult(data);
    } catch (failure) {
      if (request === requestRef.current) setError(failure?.message || "Could not load passage matches.");
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  }

  if (!controlCode) return null;

  const currentResult = result?.organization_id === organizationId &&
    result?.assessment_id === assessmentId ? result : null;
  const matches = (currentResult?.matches || []).filter((item) => item.control_code === controlCode);
  const noTerms = currentResult?.controls_without_terms?.includes(controlCode);
  const documentCount = new Set(matches.map((match) => match.evidence_file_id)).size;

  return (
    <section className="assessment-passages" aria-label={`Proposed passages for ${controlCode}`}>
      <p className="eyebrow">DOCUMENT MATCHES</p>
      <h4>Proposed passages for {controlCode}</h4>
      <p className="assessment-note">
        These proposed matches are unverified. Review the passage and source before using them as evidence.
        Finding a passage does not attach the file or change a control result.
      </p>


      <button className="secondary-button" type="button" disabled={loading} onClick={loadMatches}>
        {loading ? "Finding passages…" : currentResult ? "Refresh matches" : "Find relevant passages"}
      </button>

      {loading && <p role="status">Checking uploaded documents…</p>}
      {error && <p role="alert">{error}</p>}
      {currentResult && !loading && (
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
          ) : currentResult.files_checked === 0 ? (
            <p className="assessment-note">No uploaded documents are available to check.</p>
          ) : matches.length === 0 ? (
            <p className="assessment-note">
              {`No matching passages found in ${currentResult.files_checked} ${currentResult.files_checked === 1 ? "document" : "documents"} checked.`}
            </p>
          ) : (
            <ul aria-label={`Passages for ${controlCode}`}>
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
            {`Matcher: ${currentResult.matcher_version}. The match score ranks passages; it is not a probability that a control is implemented.`}
          </p>
        </div>
      )}
    </section>
  );
}