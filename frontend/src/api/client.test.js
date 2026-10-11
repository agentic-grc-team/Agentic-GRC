import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest } from "./client.js";

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

    await expect(apiRequest("/organizations", { accessToken: "signed-token" })).resolves.toEqual({ id: "org-1" });
    expect(fetch).toHaveBeenCalledWith("/api/v1/organizations", expect.objectContaining({
      credentials: "omit",
      headers: expect.any(Headers),
    }));
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
});
