import { DEFAULT_API_BASE_URL } from "../basePath.js";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, body) {
    const detailMessage = typeof body?.detail === "string" ? body.detail : body?.detail?.message;
    super(typeof detailMessage === "string" ? detailMessage : `Request failed (${status}).`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

let accessTokenRefresher = null;

// The auth layer registers how to obtain a renewed access token. Supabase only refreshes the
// token on a timer while the tab is visible, so a request can still carry a token that expired
// while the tab was in the background; on a 401 the request is retried once with a renewed token.
export function setAccessTokenRefresher(refresher) {
  accessTokenRefresher = refresher;
  return () => {
    if (accessTokenRefresher === refresher) {
      accessTokenRefresher = null;
    }
  };
}

async function renewedAccessToken(staleToken) {
  if (!accessTokenRefresher) {
    return null;
  }
  try {
    const token = await accessTokenRefresher(staleToken);
    return token && token !== staleToken ? token : null;
  } catch {
    return null;
  }
}

export async function apiRequest(path, { accessToken, ...options } = {}) {
  try {
    return await sendRequest(path, accessToken, options);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401 || !accessToken) {
      throw error;
    }
    const renewed = await renewedAccessToken(accessToken);
    if (!renewed) {
      throw error;
    }
    return sendRequest(path, renewed, options);
  }
}

async function sendRequest(path, accessToken, options) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");

  if (options.body instanceof FormData) {
    // The browser supplies the multipart boundary.
    headers.delete("Content-Type");
  } else if (options.body && !headers.has("Content-Type")) {
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
