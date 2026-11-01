import { apiRequest } from "../../api/client.js";

function interviewPath(organizationId, assessmentId) {
  return `/organizations/${encodeURIComponent(organizationId)}/assessments/${encodeURIComponent(assessmentId)}/interview`;
}

export function openInterview(organizationId, assessmentId, accessToken) {
  return apiRequest(interviewPath(organizationId, assessmentId), {
    method: "POST",
    accessToken,
    body: JSON.stringify({ session_type: "kickoff" }),
  });
}

export function getInterview(organizationId, assessmentId, sessionId, accessToken) {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return apiRequest(`${interviewPath(organizationId, assessmentId)}${query}`, { accessToken });
}

export function submitInterviewTurn(organizationId, assessmentId, payload, accessToken) {
  return apiRequest(`${interviewPath(organizationId, assessmentId)}/turns`, {
    method: "POST",
    accessToken,
    body: JSON.stringify(payload),
  });
}
