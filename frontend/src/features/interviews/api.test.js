import { describe, expect, it } from "vitest";

import { ApiError } from "../../api/client.js";
import { getInterview, openInterview, submitInterviewTurn } from "./api.js";

function respond(status, body) {
  fetch.mockResolvedValueOnce({ status, ok: status < 400, json: async () => body });
}

describe("interviews api", () => {
  it("opens or resumes the interview with a bearer token", async () => {
    respond(201, { session: { id: "session-1" } });

    const result = await openInterview("org-1", "assessment-1", "token");

    expect(result).toEqual({ session: { id: "session-1" } });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/v1/organizations/org-1/assessments/assessment-1/interview");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ session_type: "kickoff" });
    expect(options.headers.get("Authorization")).toBe("Bearer token");
    expect(options.headers.get("Content-Type")).toBe("application/json");
  });

  it("reads a specific session", async () => {
    respond(200, { turns: [] });

    await getInterview("org-1", "assessment-1", "session-1", "token");

    expect(fetch.mock.calls[0][0]).toBe(
      "/api/v1/organizations/org-1/assessments/assessment-1/interview?session_id=session-1",
    );
  });

  it("posts an answer to the turns endpoint", async () => {
    respond(201, { turn: { id: "turn-2" } });
    const payload = { session_id: "session-1", content: "We use MFA.", client_request_id: "request-1" };

    await submitInterviewTurn("org-1", "assessment-1", payload, "token");

    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/v1/organizations/org-1/assessments/assessment-1/interview/turns");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual(payload);
  });

  it("rejects with the API detail on failure", async () => {
    respond(409, { detail: "The assessment is not in progress." });

    const error = await openInterview("org-1", "assessment-1", "token").catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.message).toBe("The assessment is not in progress.");
  });
});
