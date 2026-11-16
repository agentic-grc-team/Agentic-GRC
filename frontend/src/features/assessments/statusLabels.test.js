import { describe, expect, it } from "vitest";

import { acceptsInterviews, assessmentStatusLabel } from "./statusLabels.js";

describe("assessmentStatusLabel", () => {
  it("labels every backend assessment status", () => {
    expect(["draft", "in_progress", "awaiting_review", "completed"].map(assessmentStatusLabel)).toEqual([
      "Draft",
      "In progress",
      "Awaiting review",
      "Completed",
    ]);
  });

  it("shows an unknown status as it is instead of hiding it", () => {
    expect(assessmentStatusLabel("archived")).toBe("archived");
  });

  it("follows the backend's accepts_interviews flag", () => {
    expect(acceptsInterviews({ status: "awaiting_review", accepts_interviews: true })).toBe(true);
    expect(acceptsInterviews({ status: "completed", accepts_interviews: false })).toBe(false);
    expect(acceptsInterviews({ status: "in_progress" })).toBe(false);
    expect(acceptsInterviews(undefined)).toBe(false);
  });
});
