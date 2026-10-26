import { describe, expect, it } from "vitest";

import { assessmentStatusLabel } from "./statusLabels.js";

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
});
