import { apiRequest } from "../../api/client.js";

export function listOrganizations(accessToken) {
  return apiRequest("/organizations", { accessToken });
}

export function listIndustrySectors(accessToken) {
  return apiRequest("/reference-data/industry-sectors", { accessToken });
}

export function listOrganizationSizes(accessToken) {
  return apiRequest("/reference-data/organization-sizes", { accessToken });
}

export function createOrganization(payload, accessToken) {
  return apiRequest("/organizations", {
    method: "POST",
    accessToken,
    body: JSON.stringify(payload),
  });
}

export function createInvitation(organizationId, email, role, accessToken) {
  return apiRequest(`/organizations/${encodeURIComponent(organizationId)}/invitations`, {
    method: "POST",
    accessToken,
    body: JSON.stringify({ email, role }),
  });
}

export function listMyInvitations(accessToken) {
  return apiRequest("/organizations/me/invitations", { accessToken });
}

export function acceptInvitation(invitationId, accessToken) {
  return apiRequest(`/organizations/invitations/${encodeURIComponent(invitationId)}/accept`, {
    method: "POST",
    accessToken,
  });
}
