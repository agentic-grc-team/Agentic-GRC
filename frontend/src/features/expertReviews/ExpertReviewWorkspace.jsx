import { useEffect, useRef, useState } from "react";

import {
  listPendingReviews,
  submitReviewDecision,
} from "./api.js";

import ReviewEvidence from "./ReviewEvidence.jsx";

function formatValue(value) {
  return value.replaceAll("_", " ");
}


const outcomeLabels = {
  accepted: "accepted",
  modified: "marked as modified",
  rejected: "rejected",
};


export default function ExpertReviewWorkspace({ accessToken, sessionId }) {
  const [reviews, setReviews] = useState([]);
  const [comment, setComment] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [isEditing, setIsEditing] = useState(false);
  const [editedStatus, setEditedStatus] = useState("");
  const [editedExplanation, setEditedExplanation] = useState("");
  const [justification, setJustification] = useState("");
  const [notAssessedReason, setNotAssessedReason] = useState("");

  const sessionRef = useRef(null);
  const accessTokenRef = useRef(accessToken);
  const sessionKey = sessionId ?? accessToken;

  useEffect(() => {
    accessTokenRef.current = accessToken;
  }, [accessToken]);

  function resetEditor() {
    setIsEditing(false);
    setEditedStatus("");
    setEditedExplanation("");
    setJustification("");
    setNotAssessedReason("");
  }

  useEffect(() => {
    let isActive = true;

    const session = {};
    sessionRef.current = session;

    setReviews([]);
    setComment("");
    setError("");
    setNotice("");
    setIsLoading(true);
    setIsSubmitting(false);

    setIsEditing(false);
    setEditedStatus("");
    setEditedExplanation("");
    setJustification("");
    setNotAssessedReason("");

    async function loadReviews() {
      try {
        const pendingReviews = await listPendingReviews(
          accessTokenRef.current,
        );

        if (isActive) {
          setReviews(pendingReviews);
        }
      } catch (requestError) {
        if (isActive) {
          setError(
            requestError.message || "Unable to load pending reviews.",
          );
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    loadReviews();

    return () => {
      isActive = false;

      if (sessionRef.current === session) {
        sessionRef.current = null;
      }
    };
  }, [sessionKey]);

  function startEditing() {
    if (reviews.length === 0 || isSubmitting) {
      return;
    }

    const review = reviews[0];

    setEditedStatus(review.control_status);
    setEditedExplanation(review.explanation);
    setJustification(review.justification || "");
    setNotAssessedReason(review.not_assessed_reason || "");
    setIsEditing(true);
    setError("");
    setNotice("");
  }

  function cancelEditing() {
    resetEditor();
    setError("");
  }

  async function handleDecision(outcome) {
    if (reviews.length === 0 || isSubmitting) {
      return;
    }

    const session = sessionRef.current;
    const resultId = reviews[0].result_id;
    const trimmedComment = comment.trim();

    setError("");
    setNotice("");

    if (
      (outcome === "modified" || outcome === "rejected") &&
      trimmedComment === ""
    ) {
      setError(
        "A review comment is required when modifying or rejecting a result.",
      );
      return;
    }

    let modifiedResult = null;

    if (outcome === "modified") {
      if (!isEditing) {
        return;
      }

      const explanation = editedExplanation.trim();

      if (explanation === "") {
        setError("An explanation is required for a modified result.");
        return;
      }

      if (
        editedStatus === "not_applicable" &&
        justification.trim() === ""
      ) {
        setError("A justification is required for not applicable.");
        return;
      }

      if (
        editedStatus === "not_assessed" &&
        notAssessedReason.trim() === ""
      ) {
        setError("A reason is required for not assessed.");
        return;
      }

      modifiedResult = {
        control_status: editedStatus,
        explanation: explanation,
      };

      if (editedStatus === "not_applicable") {
        modifiedResult.justification = justification.trim();
      }

      if (editedStatus === "not_assessed") {
        modifiedResult.not_assessed_reason = notAssessedReason.trim();
      }
    }

    setIsSubmitting(true);

    try {
      let response;

      if (outcome === "modified") {
        response = await submitReviewDecision(
          resultId,
          outcome,
          trimmedComment,
          accessTokenRef.current,
          modifiedResult,
        );
      } else {
        response = await submitReviewDecision(
          resultId,
          outcome,
          trimmedComment,
          accessTokenRef.current,
        );
      }

      if (sessionRef.current !== session) {
        return;
      }

      setNotice(
        `The result was successfully ${outcomeLabels[response.outcome]}.`,
      );

      setReviews((currentReviews) =>
        currentReviews.filter((item) => item.result_id !== resultId),
      );

      setComment("");
      resetEditor();
    } catch (requestError) {
      if (sessionRef.current === session) {
        setError(
          requestError.message || "Unable to submit review.",
        );
      }
    } finally {
      if (sessionRef.current === session) {
        setIsSubmitting(false);
      }
    }
  }

  if (isLoading) {
    return <p>Loading pending reviews...</p>;
  }

  if (error && reviews.length === 0) {
    return <p role="alert">{error}</p>;
  }

  if (reviews.length === 0) {
    return (
      <section className="expert-review-workspace">
        <p className="eyebrow">EXPERT REVIEW</p>
        <h1>Review queue complete</h1>

        {notice && <p role="status">{notice}</p>}

        <div className="review-section">
          <h3>No pending results</h3>
          <p>
            There are currently no AI-generated results waiting for
            expert review.
          </p>
        </div>
      </section>
    );
  }

  const review = reviews[0];

  return (
    <section className="expert-review-workspace">
      <p className="eyebrow">EXPERT REVIEW</p>
      <h1>{review.control_code}</h1>
      <h2>{review.control_title}</h2>

      <div className="review-summary">
        <p>
          <strong>Proposed status:</strong>{" "}
          {formatValue(review.control_status)}
        </p>

        <p>
          <strong>Current maturity:</strong>{" "}
          {review.maturity_current ?? "Not available"}
        </p>

        <p>
          <strong>AI confidence:</strong>{" "}
          {review.confidence == null
            ? "Not available"
            : `${Math.round(review.confidence * 100)}%`}
        </p>
      </div>

      <div className="review-section">
        <h3>AI explanation</h3>
        <p>{review.explanation}</p>
      </div>

      <div className="review-section">
        <h3>Evidence summary</h3>
        <p>
          {review.evidence_summary?.trim() ||
            "No evidence summary available."}
        </p>
      </div>

      <ReviewEvidence
        resultId={review.result_id}
        accessToken={accessToken}
        sessionId={sessionKey}
      />

      {isEditing && (
        <div className="review-section">
          <h3>Edit result</h3>

          <label className="review-comment">
            Modified status
            <select
              value={editedStatus}
              onChange={(event) => setEditedStatus(event.target.value)}
              disabled={isSubmitting}
            >
              <option value="implemented">Implemented</option>
              <option value="partially_implemented">
                Partially implemented
              </option>
              <option value="not_implemented">Not implemented</option>
              <option value="not_applicable">Not applicable</option>
              <option value="not_assessed">Not assessed</option>
            </select>
          </label>

          <label className="review-comment">
            Modified explanation
            <textarea
              value={editedExplanation}
              onChange={(event) =>
                setEditedExplanation(event.target.value)
              }
              disabled={isSubmitting}
              rows="5"
            />
          </label>

          {editedStatus === "not_applicable" && (
            <label className="review-comment">
              Justification for not applicable
              <textarea
                value={justification}
                onChange={(event) =>
                  setJustification(event.target.value)
                }
                disabled={isSubmitting}
                rows="3"
              />
            </label>
          )}

          {editedStatus === "not_assessed" && (
            <label className="review-comment">
              Reason for not assessed
              <textarea
                value={notAssessedReason}
                onChange={(event) =>
                  setNotAssessedReason(event.target.value)
                }
                disabled={isSubmitting}
                rows="3"
              />
            </label>
          )}
        </div>
      )}

      <label className="review-comment">
        Review comment
        <textarea
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          disabled={isSubmitting}
          rows="5"
          placeholder="Explain your review decision..."
        />
      </label>

      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}

      <div className="review-actions">
        {!isEditing && (
          <>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => handleDecision("accepted")}
            >
              Accept
            </button>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={startEditing}
            >
              Edit result
            </button>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => handleDecision("rejected")}
            >
              Reject
            </button>
          </>
        )}

        {isEditing && (
          <>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => handleDecision("modified")}
            >
              Submit modified result
            </button>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={cancelEditing}
            >
              Cancel editing
            </button>
          </>
        )}
      </div>
    </section>
  );
}