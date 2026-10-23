import { apiRequest } from "../../api/client.js";

function assessmentsPath(organizationId) {
  return `/organizations/${encodeURIComponent(organizationId)}/assessments`;
}

export function listAssessments(organizationId, accessToken) {
  return apiRequest(assessmentsPath(organizationId), { accessToken });
}

export function createAssessment(organizationId, title, accessToken) {
  return apiRequest(assessmentsPath(organizationId), {
    method: "POST",
    accessToken,
    body: JSON.stringify({ title }),
  });
}

export function getAssessmentScope(organizationId, assessmentId, accessToken) {
  return apiRequest(
    `${assessmentsPath(organizationId)}/${encodeURIComponent(assessmentId)}/scope`,
    { accessToken },
  );
}
