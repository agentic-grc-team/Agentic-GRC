import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getReportPreview } from "./api.js";
import AssessmentComparison from "./AssessmentComparison.jsx";

vi.mock("./api.js", () => ({ getReportPreview: vi.fn() }));

const assessments = [
  { id: "current", title: "November", created_at: "2026-11-19T12:00:00Z" },
  { id: "old", title: "October", created_at: "2026-10-19T12:00:00Z" },
  { id: "older", title: "September", created_at: "2026-09-19T12:00:00Z" },
  { id: "future", title: "December", created_at: "2026-12-19T12:00:00Z" },
];

const current = {
  scope: [{ code: "PR.AA-01", title: "Identity management" }, { code: "PR.AA-02", title: "Access control" }, { code: "PR.AA-03", title: "New control" }],
  results: [{ code: "PR.AA-01", status_label: "Implemented", control_status: "implemented" }],
  pending: [{ code: "PR.AA-02", reason_label: "Awaiting expert review" }],
  exclusions: [],
  summary: { coverage_pct: 33.3 },
};

const old = {
  scope: [{ code: "PR.AA-01", title: "Identity management" }, { code: "PR.AA-02", title: "Access control" }, { code: "PR.AA-04", title: "Retired control" }],
  results: [
    { code: "PR.AA-01", status_label: "Not implemented", control_status: "not_implemented" },
    { code: "PR.AA-02", status_label: "Partially implemented", control_status: "partially_implemented" },
  ],
  pending: [], exclusions: [], summary: { coverage_pct: 66.7 },
};

function view(props = {}) {
  return render(<AssessmentComparison organizationId="org-1" currentAssessmentId="current" assessments={assessments} current={current} accessToken="token-a" {...props} />);
}

describe("Assessment comparison", () => {
  beforeEach(() => { getReportPreview.mockReset(); getReportPreview.mockResolvedValue(old); });

  it("compares finalized statuses on shared controls without grading pending or changed scope", async () => {
    view();
    const select = screen.getByRole("combobox", { name: "Previous assessment" });
    expect(within(select).getByRole("option", { name: "Select an assessment" })).toBeDisabled();
    expect(within(select).queryByRole("option", { name: "December" })).not.toBeInTheDocument();
    fireEvent.change(select, { target: { value: "old" } });

    const table = await screen.findByRole("table", { name: "Control status comparison" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Not implementedImplementedImproved");
    expect(rows[1]).toHaveTextContent("Partially implementedAwaiting expert reviewNot comparable");
    expect(screen.getByText(/2 shared controls · 1 new in this scope · 1 only in the previous scope/)).toBeInTheDocument();
    expect(screen.getByText(/66.7% previously → 33.3% now/)).toBeInTheDocument();
    expect(getReportPreview).toHaveBeenCalledWith("org-1", "old", "token-a");
  });

  it("ignores a late response after choosing another previous assessment", async () => {
    let resolveFirst;
    getReportPreview.mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve; }));
    view();
    const select = screen.getByRole("combobox", { name: "Previous assessment" });
    fireEvent.change(select, { target: { value: "old" } });
    fireEvent.change(select, { target: { value: "older" } });
    await screen.findByRole("table", { name: "Control status comparison" });
    await act(async () => { resolveFirst({ ...old, summary: { coverage_pct: 5 } }); });
    expect(screen.queryByText(/5.0% previously/)).not.toBeInTheDocument();
    await waitFor(() => expect(getReportPreview).toHaveBeenLastCalledWith("org-1", "older", "token-a"));
  });

  it("explains when there is no earlier assessment", () => {
    view({ assessments: [assessments[0]] });
    expect(screen.getByText("No earlier assessments are available for this organization.")).toBeInTheDocument();
    expect(getReportPreview).not.toHaveBeenCalled();
  });
});
