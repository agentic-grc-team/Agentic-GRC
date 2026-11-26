import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getAssessmentComparison, getComparisonCandidates } from "./api.js";
import AssessmentComparison from "./AssessmentComparison.jsx";

vi.mock("./api.js", () => ({
  getAssessmentComparison: vi.fn(),
  getComparisonCandidates: vi.fn(),
}));

const candidates = [
  { id: "old", title: "October", completed_at: "2026-10-20T12:00:00Z" },
  { id: "older", title: "September", completed_at: "2026-09-20T12:00:00Z" },
];

const comparison = {
  current: { id: "current", compliance: { available: true, value_pct: 75 } },
  previous: { id: "old", compliance: { available: true, value_pct: 62.5 } },
  compliance_change_pct: 12.5,
  warnings: [
    { code: "framework_differs", message: "The assessments use different frameworks." },
    { code: "kb_version_differs", message: "The knowledge base versions differ." },
    { code: "scope_differs", message: "The scope differs." },
  ],
  scope: { added: ["PR.AA-05"], removed: ["PR.AA-04"], common: 2 },
  controls: [
    {
      code: "PR.AA-01",
      title: "Identity management",
      previous_status: "not_implemented",
      current_status: "implemented",
      change: "improved",
    },
    {
      code: "PR.AA-02",
      title: "Access control",
      previous_status: "partially_implemented",
      current_status: "pending",
      change: "not_comparable",
    },
  ],
};

function view(props = {}) {
  return render(
    <AssessmentComparison
      organizationId="org-1"
      currentAssessmentId="current"
      current={{ assessment: { status: "completed" } }}
      accessToken="token-a"
      {...props}
    />,
  );
}

describe("Assessment comparison", () => {
  beforeEach(() => {
    getComparisonCandidates.mockReset();
    getAssessmentComparison.mockReset();
    getComparisonCandidates.mockResolvedValue(candidates);
    getAssessmentComparison.mockResolvedValue(comparison);
  });

  it("uses the server's completed candidates and comparison, including compliance and version warnings", async () => {
    view();
    const select = await screen.findByRole("combobox", { name: "Previous assessment" });
    expect(within(select).getByRole("option", { name: "Select an assessment" })).toBeDisabled();
    expect(within(select).queryByRole("option", { name: "December" })).not.toBeInTheDocument();
    expect(getComparisonCandidates).toHaveBeenCalledWith("org-1", "current", "token-a");
    expect(getAssessmentComparison).not.toHaveBeenCalled();

    fireEvent.change(select, { target: { value: "old" } });
    const table = await screen.findByRole("table", { name: "Control status comparison" });
    expect(getAssessmentComparison).toHaveBeenCalledWith("org-1", "current", "old", "token-a");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Not implementedImplementedImproved");
    expect(rows[1]).toHaveTextContent("Partially implementedPending reviewNot comparable");
    expect(
      screen.getByText(/2 shared controls · 1 new in this scope · 1 only in the previous scope/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Compliance: 62.5% previously → 75.0% now. Change: \+12.5 percentage points./,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("The assessments use different frameworks.")).toBeInTheDocument();
    expect(screen.getByText("The knowledge base versions differ.")).toBeInTheDocument();
    expect(screen.queryByText(/Review coverage:/)).not.toBeInTheDocument();
  });

  it("warns that a current assessment still in progress can change", async () => {
    view({ current: { assessment: { status: "in_progress" } } });
    expect(screen.getByText(/This assessment is not completed yet/)).toBeInTheDocument();
    expect(
      await screen.findByRole("combobox", { name: "Previous assessment" }),
    ).toBeInTheDocument();
  });

  it("ignores a late comparison from another previous assessment", async () => {
    let resolveFirst;
    getAssessmentComparison
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
      )
      .mockResolvedValueOnce({
        ...comparison,
        previous: { ...comparison.previous, id: "older" },
      });
    view();
    const select = await screen.findByRole("combobox", { name: "Previous assessment" });
    fireEvent.change(select, { target: { value: "old" } });
    fireEvent.change(select, { target: { value: "older" } });
    expect(await screen.findByText(/Compliance: 62.5% previously/)).toBeInTheDocument();
    await act(async () => {
      resolveFirst({
        ...comparison,
        previous: { ...comparison.previous, compliance: { available: true, value_pct: 5 } },
      });
    });
    await waitFor(() =>
      expect(getAssessmentComparison).toHaveBeenLastCalledWith(
        "org-1",
        "current",
        "older",
        "token-a",
      ),
    );
    expect(screen.queryByText(/5.0% previously/)).not.toBeInTheDocument();
  });

  it("shows an empty state only when the server returns no completed candidates", async () => {
    getComparisonCandidates.mockResolvedValueOnce([]);
    view();
    expect(
      await screen.findByText(
        "No earlier completed assessments are available for this organization.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Previous assessment" })).not.toBeInTheDocument();
  });

  it("lets the user retry a failed candidate request", async () => {
    getComparisonCandidates.mockRejectedValueOnce(new Error("Network error"));
    view();
    expect(await screen.findByRole("alert")).toHaveTextContent("Network error");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("combobox", { name: "Previous assessment" }),
    ).toBeInTheDocument();
  });

  it("shows unavailable compliance without inventing a change", async () => {
    getAssessmentComparison.mockResolvedValueOnce({
      ...comparison,
      current: { id: "current", compliance: { available: false, value_pct: null } },
      compliance_change_pct: null,
      warnings: [
        { code: "compliance_unavailable", message: "The compliance figure is unavailable." },
      ],
    });
    view();
    fireEvent.change(await screen.findByRole("combobox", { name: "Previous assessment" }), {
      target: { value: "old" },
    });
    expect(
      await screen.findByText(/Compliance: 62.5% previously → Unavailable now./),
    ).toBeInTheDocument();
    expect(screen.getByText("The compliance figure is unavailable.")).toBeInTheDocument();
    expect(screen.queryByText(/percentage points/)).not.toBeInTheDocument();
  });
});
