import { expect, it } from "vitest";

import { getReviewEvidence, getReviewTrace } from "./api.js";


it("loads review evidence with the current bearer token", async () => {
  const evidence = {
    result_id: "result-1",
    sources: [],
    linked_documents: [],
    evidence_pending: false,
    skipped_source_count: 0,
  };

  fetch.mockResolvedValueOnce({
    status: 200,
    ok: true,
    json: async () => evidence,
  });

  const result = await getReviewEvidence(
    "result-1",
    "test-token",
  );

  expect(result).toEqual(evidence);

  const [url, options] = fetch.mock.calls[0];

  expect(url).toBe(
    "/api/v1/expert-reviews/result-1/evidence",
  );

  expect(
    options.headers.get("Authorization"),
  ).toBe("Bearer test-token");

  expect(options.credentials).toBe("omit");
});

it("getReviewTrace requests the trace of one result with the bearer token", async () => {
  const trace = { result_id: "result 1", steps: [] };

  fetch.mockResolvedValueOnce({
    status: 200,
    ok: true,
    json: async () => trace,
  });

  const result = await getReviewTrace("result 1", "test-token");

  expect(result).toEqual(trace);

  const [url, options] = fetch.mock.calls[0];

  expect(url).toBe("/api/v1/expert-reviews/result%201/trace");
  expect(options.headers.get("Authorization")).toBe("Bearer test-token");
  expect(options.credentials).toBe("omit");
});
