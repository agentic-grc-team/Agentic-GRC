import { useEffect, useRef, useState } from "react";

import { getReviewEvidence } from "./api.js";

function formatFileSize(bytes) {
  if (bytes < 1000) {
    return `${bytes} bytes`;
  }

  if (bytes < 1000000) {
    return `${(bytes / 1000).toFixed(1)} KB`;
  }

  return `${(bytes / 1000000).toFixed(1)} MB`;
}

export default function ReviewEvidence({ resultId, accessToken, sessionId }) {
  const [response, setResponse] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const accessTokenRef = useRef(accessToken);
  const sessionKey = sessionId ?? accessToken;

  useEffect(() => {
    accessTokenRef.current = accessToken;
  }, [accessToken]);

  useEffect(() => {
    let active = true;
    setResponse(null);

    async function loadEvidence() {
      try {
        const evidence = await getReviewEvidence(
          resultId,
          accessTokenRef.current,
        );

        if (active) {
          setResponse({ resultId, sessionKey, evidence });
        }
      } catch {
        if (active) {
          setResponse({ resultId, sessionKey, error: true });
        }
      }
    }

    loadEvidence();

    return () => {
      active = false;
    };
  }, [resultId, sessionKey, attempt]);

  // Hide old data immediately when the result or session changes.
  let current = null;

  if (
    response?.resultId === resultId &&
    response?.sessionKey === sessionKey
  ) {
    current = response;
  }

  if (!current) {
    return (
      <div className="review-section">
        <h3>Evidence and sources</h3>
        <p>Loading evidence and sources...</p>
      </div>
    );
  }

  if (current.error) {
    return (
      <div className="review-section">
        <h3>Evidence and sources</h3>

        <p role="alert">
          Unable to load evidence and sources.
          This does not mean evidence is absent.
        </p>

        <button
          type="button"
          onClick={() => setAttempt(attempt + 1)}
        >
          Retry evidence
        </button>
      </div>
    );
  }

  const evidence = current.evidence;

  const documentSources = evidence.sources.filter(
    (item) => item.source_type === "document_span",
  );

  const interviews = evidence.sources.filter(
    (item) => item.source_type === "interview_turn",
  );

  const otherSources = evidence.sources.filter(
    (item) => item.source_type === "other",
  );

  return (
    <div className="review-section review-evidence">
      <h3>Evidence and sources</h3>

      {evidence.evidence_pending && (
        <p>
          <strong>Additional evidence requested.</strong>
        </p>
      )}

      <h4>Documents linked to this control</h4>

      <p>
        Attached documents still need consultant verification.
        Current attachments can differ from the sources cited
        when the AI result was saved.
      </p>

      {evidence.linked_documents.length === 0 ? (
        <p>No documents are currently linked to this control.</p>
      ) : (
        <ul>
          {evidence.linked_documents.map((document) => (
            <li key={document.id}>
              <strong>{document.original_filename}</strong>{" "}
              <span>
                ({formatFileSize(document.size_bytes)}
                {document.content_type && `, ${document.content_type}`})
              </span>
            </li>
          ))}
        </ul>
      )}

      <h4>Document sources cited by the AI</h4>

      {documentSources.length === 0 ? (
        <p>No document sources were recorded for this result.</p>
      ) : (
        <ul>
          {documentSources.map((source) => (
            <li key={source.reference}>
              <strong>
                {source.document?.original_filename ||
                  "Document unavailable in this assessment context"}
              </strong>

              <p className="review-source-reference">
                {source.reference}
              </p>

              {source.excerpt && (
                <blockquote>{source.excerpt}</blockquote>
              )}
            </li>
          ))}
        </ul>
      )}

      <h4>Interview statements</h4>

      <p>
        Statements from the interview are attestations, not
        documentary evidence. Excerpts below are saved citations,
        not a verified transcript lookup.
      </p>

      {interviews.length === 0 ? (
        <p>No interview sources were recorded for this result.</p>
      ) : (
        <ul>
          {interviews.map((source) => (
            <li key={source.reference}>
              <span className="review-source-reference">
                {source.reference}
              </span>

              {source.excerpt ? (
                <blockquote>{source.excerpt}</blockquote>
              ) : (
                <p>No saved excerpt available.</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {otherSources.length > 0 && (
        <>
          <h4>Other source references</h4>

          <ul>
            {otherSources.map((source) => (
              <li key={source.reference}>
                {source.reference} — source not resolved
              </li>
            ))}
          </ul>
        </>
      )}

      {evidence.skipped_source_count > 0 && (
        <p>Some saved source entries could not be displayed.</p>
      )}
    </div>
  );
}