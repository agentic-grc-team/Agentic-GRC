const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, body) {
    const detailMessage = typeof body?.detail === "string" ? body.detail : body?.detail?.message;
    super(typeof detailMessage === "string" ? detailMessage : `Request failed (${status}).`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export async function apiRequest(path, { accessToken, ...options } = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let response;
  try {
    response = await fetch(`${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`, {
      ...options,
      headers,
      credentials: "omit",
    });
  } catch {
    throw new Error("Could not reach the API. Check that the backend is running.");
  }

  if (response.status === 204) {
    return null;
  }

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, body);
  }
  return body;
}

export async function checkApiHealth() {
  return apiRequest("/health");
}
