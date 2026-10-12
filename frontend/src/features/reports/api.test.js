import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client.js";
import { DEMO_ASSESSMENT_ID, downloadReportPdf, getReportPreview } from "./api.js";

describe("reports api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls getReportPreview with encoded path and bearer token", async () => {
    fetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => ({ is_demo_data: true }),
    });

    const result = await getReportPreview("org-1", DEMO_ASSESSMENT_ID, "test-token");
    expect(result).toEqual({ is_demo_data: true });
    expect(fetch).toHaveBeenCalledWith(
      `/api/v1/organizations/org-1/assessments/${DEMO_ASSESSMENT_ID}/report`,
      expect.objectContaining({
        credentials: "omit",
        headers: expect.any(Headers),
      })
    );
    const [, options] = fetch.mock.calls[0];
    expect(options.headers.get("Authorization")).toBe("Bearer test-token");
    expect(options.headers.get("Accept")).toBe("application/json");
  });

  it("calls downloadReportPdf with pdf url, headers, and returns blob with parsed filename", async () => {
    const mockBlob = new Blob(["%PDF-1.4 test"], { type: "application/pdf" });
    fetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      headers: new Headers({
        "Content-Disposition": 'attachment; filename="custom-report-name.pdf"',
      }),
      blob: async () => mockBlob,
    });

    const result = await downloadReportPdf("org-1", "assess-1", "token-xyz");
    expect(result.blob).toBe(mockBlob);
    expect(result.filename).toBe("custom-report-name.pdf");

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/organizations/org-1/assessments/assess-1/report.pdf",
      expect.objectContaining({
        method: "GET",
        credentials: "omit",
        headers: expect.any(Headers),
      })
    );
    const [, options] = fetch.mock.calls[0];
    expect(options.headers.get("Authorization")).toBe("Bearer token-xyz");
    expect(options.headers.get("Accept")).toBe("application/pdf");
  });

  it("falls back to default filename when Content-Disposition is missing", async () => {
    const mockBlob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    fetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      headers: new Headers({}),
      blob: async () => mockBlob,
    });

    const result = await downloadReportPdf("org-1", "assess-123", "token-abc");
    expect(result.filename).toBe("agentic-grc-report-assess-123.pdf");
    expect(result.blob).toBe(mockBlob);
  });

  it("rejects with ApiError carrying status and detail message on non-ok response", async () => {
    fetch.mockResolvedValueOnce({
      status: 404,
      ok: false,
      json: async () => ({ detail: "Assessment not found." }),
    });

    const error = await downloadReportPdf("org-1", "assess-1", "token").catch((err) => err);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.message).toBe("Assessment not found.");
  });

  it("rejects with standard message when fetch throws", async () => {
    fetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(downloadReportPdf("org-1", "assess-1", "token")).rejects.toThrow(
      "Could not reach the API. Check that the backend is running."
    );
  });
});
