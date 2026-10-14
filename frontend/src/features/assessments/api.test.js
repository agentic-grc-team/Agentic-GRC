import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client.js";
import { listAssessments } from "./api.js";

describe("assessments api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls listAssessments with encoded path and bearer token", async () => {
    fetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => [{ id: "assess-1", title: "Assessment 1" }],
    });

    const result = await listAssessments("org-1", "test-token");
    expect(result).toEqual([{ id: "assess-1", title: "Assessment 1" }]);
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/organizations/org-1/assessments",
      expect.objectContaining({
        credentials: "omit",
        headers: expect.any(Headers),
      })
    );
    const [, options] = fetch.mock.calls[0];
    expect(options.headers.get("Authorization")).toBe("Bearer test-token");
    expect(options.headers.get("Accept")).toBe("application/json");
  });

  it("rejects with ApiError carrying status and detail message on non-ok response", async () => {
    fetch.mockResolvedValueOnce({
      status: 401,
      ok: false,
      json: async () => ({ detail: "Unauthorized" }),
    });

    const error = await listAssessments("org-1", "test-token").catch((err) => err);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(401);
    expect(error.message).toBe("Unauthorized");
  });
});
