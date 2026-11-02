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

export function listAssessmentControls(organizationId, assessmentId, accessToken) {
  return apiRequest(
    `${assessmentsPath(organizationId)}/${encodeURIComponent(assessmentId)}/controls`,
    { accessToken },
  );
}

function evidenceQuery(organizationId, assessmentId) {
  return `organization_id=${encodeURIComponent(organizationId)}&assessment_id=${encodeURIComponent(assessmentId)}`;
}

export function listAssessmentEvidence(organizationId, assessmentId, accessToken) {
  return apiRequest(`/evidence/?${evidenceQuery(organizationId, assessmentId)}`, { accessToken });
}

export function listEvidenceLinks(organizationId, assessmentId, accessToken) {
  return apiRequest(`/evidence/links?${evidenceQuery(organizationId, assessmentId)}`, { accessToken });
}

export function linkEvidence(organizationId, evidenceId, assessmentControlId, accessToken) {
  return apiRequest(`/evidence/${encodeURIComponent(evidenceId)}/controls`, {
    method: "POST",
    accessToken,
    body: JSON.stringify({
      organization_id: organizationId,
      assessment_control_id: assessmentControlId,
    }),
  });
}

export function unlinkEvidence(organizationId, evidenceId, assessmentControlId, accessToken) {
  return apiRequest(
    `/evidence/${encodeURIComponent(evidenceId)}/controls/${encodeURIComponent(assessmentControlId)}`
      + `?organization_id=${encodeURIComponent(organizationId)}`,
    { method: "DELETE", accessToken },
  );
}
