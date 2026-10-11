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
) {
  return apiRequest(`/expert-reviews/${resultId}/decision`, {
    method: "POST",
    accessToken: accessToken,
    body: JSON.stringify({
      outcome: outcome,
      comment: comment,
    }),
  });
}