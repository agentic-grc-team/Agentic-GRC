import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest, setAccessTokenRefresher } from "./client.js";

function reply(status, body = {}) {
  return { status, ok: status >= 200 && status < 300, json: async () => body };
}

describe("apiRequest", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends the access token without including browser credentials", async () => {
    fetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => ({ id: "org-1" }),
    });

    await expect(apiRequest("/organizations", { accessToken: "signed-token" })).resolves.toEqual({
      id: "org-1",
    });
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/organizations",
      expect.objectContaining({
        credentials: "omit",
        headers: expect.any(Headers),
      }),
    );
    const [, options] = fetch.mock.calls[0];
    expect(options.headers.get("Authorization")).toBe("Bearer signed-token");
  });

  it("preserves API error details for duplicate-name confirmation", async () => {
    fetch.mockResolvedValueOnce({
      status: 409,
      ok: false,
      json: async () => ({ detail: { code: "duplicate_name_requires_confirmation", matches: [] } }),
    });

    const error = await apiRequest("/organizations").catch((caught) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      body: { detail: { code: "duplicate_name_requires_confirmation" } },
    });
  });

  it("lets the browser set the multipart boundary and preserves authentication", async () => {
    fetch.mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({}) });
    const body = new FormData();
    body.append("organization_id", "alpha");
    body.append("file", new File(["evidence"], "policy.txt"));
    await apiRequest("/evidence/", {
      method: "POST",
      accessToken: "signed-token",
      body,
      headers: { "Content-Type": "application/json" },
    });
    const [, options] = fetch.mock.calls[0];
    expect(options.body).toBe(body);
    expect(options.headers.has("Content-Type")).toBe(false);
    expect(options.headers.get("Authorization")).toBe("Bearer signed-token");
    expect(options.credentials).toBe("omit");
  });

  describe("after a 401", () => {
    let unregister = () => {};
    afterEach(() => unregister());

    it("retries once with a renewed token and the same request", async () => {
      const refresher = vi.fn().mockResolvedValue("fresh-token");
      unregister = setAccessTokenRefresher(refresher);
      fetch
        .mockResolvedValueOnce(reply(401, { detail: "A valid Supabase session is required." }))
        .mockResolvedValueOnce(reply(201, { id: "turn-2" }));

      const body = JSON.stringify({ content: "We use MFA.", client_request_id: "request-1" });
      await expect(
        apiRequest("/turns", { method: "POST", accessToken: "stale-token", body }),
      ).resolves.toEqual({ id: "turn-2" });

      expect(refresher).toHaveBeenCalledWith("stale-token");
      expect(fetch).toHaveBeenCalledTimes(2);
      const [, retry] = fetch.mock.calls[1];
      expect(retry.headers.get("Authorization")).toBe("Bearer fresh-token");
      expect(retry.method).toBe("POST");
      expect(retry.body).toBe(body);
    });

    it("returns the 401 when the session cannot be renewed", async () => {
      unregister = setAccessTokenRefresher(vi.fn().mockResolvedValue(null));
      fetch.mockResolvedValueOnce(reply(401, { detail: "A valid Supabase session is required." }));

      const request = apiRequest("/organizations", { accessToken: "stale-token" });
      await expect(request).rejects.toMatchObject({ status: 401 });
      expect(fetch).toHaveBeenCalledTimes(1);
    });

    it("does not retry when the refresher returns the same token or fails", async () => {
      unregister = setAccessTokenRefresher(vi.fn().mockResolvedValue("stale-token"));
      fetch.mockResolvedValueOnce(reply(401));
      await expect(
        apiRequest("/organizations", { accessToken: "stale-token" }),
      ).rejects.toBeInstanceOf(ApiError);

      unregister = setAccessTokenRefresher(vi.fn().mockRejectedValue(new Error("offline")));
      fetch.mockResolvedValueOnce(reply(401));
      await expect(
        apiRequest("/organizations", { accessToken: "stale-token" }),
      ).rejects.toMatchObject({ status: 401 });
      expect(fetch).toHaveBeenCalledTimes(2);
    });

    it("leaves other errors and unauthenticated requests alone", async () => {
      const refresher = vi.fn().mockResolvedValue("fresh-token");
      unregister = setAccessTokenRefresher(refresher);
      fetch.mockResolvedValueOnce(reply(403)).mockResolvedValueOnce(reply(401));

      await expect(apiRequest("/organizations", { accessToken: "token" })).rejects.toMatchObject({
        status: 403,
      });
      await expect(apiRequest("/auth/invitations/accept")).rejects.toMatchObject({ status: 401 });
      expect(refresher).not.toHaveBeenCalled();
      expect(fetch).toHaveBeenCalledTimes(2);
    });
  });
});
