import { ApiError, apiRequest } from "../../api/client.js";

export const DEMO_ASSESSMENT_ID = "00000000-0000-4000-8000-000000000014";

// Duplicated from client.js so client.js is not modified
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");

function reportPath(organizationId, assessmentId) {
  return `/organizations/${encodeURIComponent(organizationId)}/assessments/${encodeURIComponent(assessmentId)}/report`;
}

export function getReportPreview(organizationId, assessmentId, accessToken) {
  return apiRequest(reportPath(organizationId, assessmentId), { accessToken });
}

export async function downloadReportPdf(organizationId, assessmentId, accessToken) {
  const headers = new Headers();
  headers.set("Accept", "application/pdf");
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const url = `${apiBaseUrl}${reportPath(organizationId, assessmentId)}.pdf`;

  let response;
  try {
    response = await fetch(url, {
      method: "GET",
      headers,
      credentials: "omit",
    });
  } catch {
    throw new Error("Could not reach the API. Check that the backend is running.");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body);
  }

  const blob = await response.blob();
  const disposition = response.headers?.get?.("Content-Disposition");
  const match = typeof disposition === "string" ? disposition.match(/filename="?([^";]+)"?/i) : null;
  const filename = match ? match[1] : `agentic-grc-report-${assessmentId}.pdf`;

  return { blob, filename };
}
