import { useEffect, useState } from "react";

import {
  listPendingReviews,
  submitReviewDecision,
} from "./api.js";

function formatValue(value) {
  return value.replaceAll("_", " ");
}

const outcomeLabels = {
  accepted: "accepted",
  modified: "marked as modified",
  rejected: "rejected",
};

export default function ExpertReviewWorkspace({ accessToken }) {
  const [reviews, setReviews] = useState([]);
  const [comment, setComment] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let isActive = true;

    setReviews([]);
    setComment("");
    setError("");
    setNotice("");
    setIsLoading(true);

    async function loadReviews() {
      try {
        const pendingReviews = await listPendingReviews(accessToken);

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
    };
  }, [accessToken]);

  async function handleDecision(outcome) {
  if (reviews.length === 0) {
    return;
  }

  const trimmedComment = comment.trim();

  if (
    (outcome === "modified" || outcome === "rejected") &&
    trimmedComment === ""
  ) {
    setError("A review comment is required when modifying or rejecting a result.");
    setNotice("");
    return;
  }

  setIsSubmitting(true);
  setError("");
  setNotice("");

  try {
    const response = await submitReviewDecision(
      reviews[0].result_id,
      outcome,
      trimmedComment,
      accessToken,
    );

    setNotice(
      `The result was successfully ${outcomeLabels[response.outcome]}.`,
    );

    setReviews((currentReviews) => currentReviews.slice(1));
    setComment("");
  } catch (requestError) {
    setError(requestError.message);
  } finally {
    setIsSubmitting(false);
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
        <p>There are currently no AI-generated results waiting for expert review.</p>
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
          {review.maturity_current}
        </p>

        <p>
          <strong>AI confidence:</strong>{" "}
          {Math.round(review.confidence * 100)}%
        </p>
      </div>

      <div className="review-section">
        <h3>AI explanation</h3>
        <p>{review.explanation}</p>
      </div>

      <div className="review-section">
        <h3>Evidence summary</h3>
        <p>{review.evidence_summary}</p>
      </div>

      <label className="review-comment">
        Review comment
        <textarea
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          rows="5"
          disabled={isSubmitting}
          placeholder="Explain your review decision..."
        />
      </label>

      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}

      <div className="review-actions">
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
          onClick={() => handleDecision("modified")}
        >
          Mark as modified
        </button>

        <button
          type="button"
          disabled={isSubmitting}
          onClick={() => handleDecision("rejected")}
        >
          Reject
        </button>
      </div>
    </section>
  );
}