import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client.js";
import { createAssessment, getAssessmentScope, listAssessments } from "./api.js";

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

  it("creates an assessment with a POST that sends only the title", async () => {
    fetch.mockResolvedValueOnce({
      status: 201,
      ok: true,
      json: async () => ({ id: "assess-2", title: "Q4 review" }),
    });

    const result = await createAssessment("org 1", "Q4 review", "test-token");

    expect(result).toEqual({ id: "assess-2", title: "Q4 review" });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/v1/organizations/org%201/assessments");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ title: "Q4 review" });
    expect(options.headers.get("Authorization")).toBe("Bearer test-token");
    expect(options.headers.get("Content-Type")).toBe("application/json");
  });

  it("reads the scope of one assessment", async () => {
    fetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => ({ control_count: 3, functions: [] }),
    });

    const result = await getAssessmentScope("org-1", "assess/1", "test-token");

    expect(result).toEqual({ control_count: 3, functions: [] });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/v1/organizations/org-1/assessments/assess%2F1/scope");
    expect(options.headers.get("Authorization")).toBe("Bearer test-token");
  });
});
