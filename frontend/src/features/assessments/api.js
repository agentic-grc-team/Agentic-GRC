import { apiRequest } from "../../api/client.js";

export function listAssessments(organizationId, accessToken) {
  return apiRequest(`/organizations/${encodeURIComponent(organizationId)}/assessments`, { accessToken });
}
