import { describe, expect, it } from "vitest";
import { createBasePath, normalizeBase } from "./basePath";

describe("normalizeBase", () => {
  it("treats the domain root as no prefix", () => {
    expect(normalizeBase("/")).toBe("");
    expect(normalizeBase("")).toBe("");
    expect(normalizeBase(undefined)).toBe("");
  });

  it("strips extra slashes from a sub-path", () => {
    expect(normalizeBase("/agentic-grc/")).toBe("/agentic-grc");
    expect(normalizeBase("/agentic-grc")).toBe("/agentic-grc");
    expect(normalizeBase("agentic-grc/")).toBe("/agentic-grc");
  });
});

describe.each(["/agentic-grc/", "/agentic-grc"])("createBasePath(%s)", (base) => {
  const { toAppPath, toBrowserPath, assetUrl } = createBasePath(base);

  it("maps browser paths to app paths", () => {
    expect(toAppPath("/agentic-grc/evidence")).toBe("/evidence");
    expect(toAppPath("/agentic-grc/")).toBe("/");
    expect(toAppPath("/agentic-grc")).toBe("/");
    expect(toAppPath("/agentic-grc-other")).toBe("/agentic-grc-other");
    expect(toAppPath("/other")).toBe("/other");
  });

  it("maps app paths to browser paths, keeping query strings", () => {
    expect(toBrowserPath("/")).toBe("/agentic-grc/");
    expect(toBrowserPath("/evidence?organization_id=1")).toBe(
      "/agentic-grc/evidence?organization_id=1",
    );
    expect(toBrowserPath("auth/callback")).toBe("/agentic-grc/auth/callback");
  });

  it("builds public asset URLs", () => {
    expect(assetUrl("avatars/a.png")).toBe("/agentic-grc/avatars/a.png");
    expect(assetUrl("/avatars/a.png")).toBe("/agentic-grc/avatars/a.png");
  });
});

describe("createBasePath('/')", () => {
  const { toAppPath, toBrowserPath, assetUrl } = createBasePath("/");

  it("leaves paths unchanged at the domain root", () => {
    expect(toAppPath("/evidence")).toBe("/evidence");
    expect(toAppPath("/")).toBe("/");
    expect(toBrowserPath("/")).toBe("/");
    expect(toBrowserPath("/evidence")).toBe("/evidence");
    expect(assetUrl("avatars/a.png")).toBe("/avatars/a.png");
  });
});
