import { statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const asset = (name) => resolve(process.cwd(), "public", "avatars", name);

describe("interview avatar download size", () => {
  it("keeps the background and replacement poses within the first-load budget", () => {
    expect(statSync(asset("interview-office.webp")).size).toBeLessThan(500_000);
    for (const pose of [
      "interview-guide.webp",
      "interview-guide-smile.webp",
      "interview-guide-attentive.webp",
      "interview-guide-blink.webp",
      "interview-guide-thinking.webp",
    ]) {
      expect(statSync(asset(pose)).size).toBeLessThan(250_000);
    }
  });
});
