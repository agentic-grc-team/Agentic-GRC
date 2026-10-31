import { beforeEach, describe, expect, it, vi } from "vitest";
import { listOrganizations, uploadEvidence } from "./api.js";

beforeEach(() => {
  vi.resetAllMocks();
  fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
});

describe("evidence API", () => {
  it("requests active memberships only when specified", async () => {
    await listOrganizations("token", { activeMembershipsOnly: true });
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/organizations?active_memberships_only=true");
    await listOrganizations("token");
    expect(fetch.mock.calls[1][0]).toBe("/api/v1/organizations");
  });

  it("sends the selected organization and file in a multipart request", async () => {
    const file = new File(["evidence"], "policy.txt");
    const controller = new AbortController();
    await uploadEvidence("beta", file, "token", controller.signal);
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/v1/evidence/");
    expect(options.body.get("organization_id")).toBe("beta");
    expect(options.body.get("file").name).toBe("policy.txt");
    expect(options.signal).toBe(controller.signal);
    expect(options.headers.has("Content-Type")).toBe(false);
    expect(options.body.has("assessment_id")).toBe(false);
  });

  it("sends the assessment an evidence file belongs to", async () => {
    await uploadEvidence("beta", new File(["evidence"], "policy.txt"), "token", undefined, "assess-1");
    expect(fetch.mock.calls[0][1].body.get("assessment_id")).toBe("assess-1");
  });
});
