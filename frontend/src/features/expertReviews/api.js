import { apiRequest } from "../../api/client.js";


export function listPendingReviews(accessToken) {
  return apiRequest("/expert-reviews/pending", {
    accessToken: accessToken,
  });
}


export function submitReviewDecision(
  resultId,
  outcome,
  comment,
  accessToken,
  modifiedResult = null,
) {
  const payload = {
    outcome: outcome,
    comment: comment,
  };

  if (modifiedResult !== null) {
    payload.modified_result = modifiedResult;
  }

  return apiRequest(`/expert-reviews/${resultId}/decision`, {
    method: "POST",
    accessToken: accessToken,
    body: JSON.stringify(payload),
  });
}

export function getReviewEvidence(resultId, accessToken) {
  return apiRequest(`/expert-reviews/${resultId}/evidence`, {
    accessToken: accessToken,
  });
}