import { apiRequest } from "../api/client.js";

export function signInWithPassword(email, password) {
  return apiRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getCurrentAccount(accessToken) {
  return apiRequest("/auth/me", { accessToken });
}

export function acceptInvitationProfile(token, password) {
  return apiRequest("/auth/accept-invitation", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
}
