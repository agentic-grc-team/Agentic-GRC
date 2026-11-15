import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { getGapList } from "./api.js";
import GapList from "./GapList.jsx";

vi.mock("./api.js", async (importOriginal) => ({
  ...(await importOriginal()),
  getGapList: vi.fn(),
}));

const gapList = {
  organization_id: "org-1",
  assessment_id: "assessment-1",
  generated_at: "2026-11-15T12:00:00Z",
  rules_id: "rule:risk-classification",
  rules_version: "0.1",
  rules_provisional: true,
  pending_controls: 1,
  gaps: [
    {
      control_code: "PR.AA-03",
      control_title: "Users are authenticated",
      control_status: "not_implemented",
      status_label: "Not implemented",
      classified: true,
      priority: "High",
      risks: [
        { name: "Unauthorized access", severity: "Extreme" },
        { name: "System compromise", severity: "Extreme" },
      ],
      reason: "Authentication of administrator accounts governs privileged access.",
      result_version: 1,
      basis: "accepted_agent_result",
      explanation: "MFA is not enforced.",
      evidence_pending: false,
    },
    {
      control_code: "PR.AA-01",
      control_title: "Identities are managed",
      control_status: "partially_implemented",
      status_label: "Partially implemented",
      classified: false,
      priority: null,
      risks: [],
      reason: null,
      result_version: 2,
      basis: "consultant_version",
      explanation: "Leavers are disabled late.",
      evidence_pending: false,
    },
  ],
};

function renderGapList() {
  return render(<GapList organizationId="org-1" assessmentId="assessment-1" accessToken="token-1" />);
}

describe("GapList", () => {
  it("lists the gaps in the order the API returns them, with their classification", async () => {
    getGapList.mockResolvedValueOnce(gapList);

    renderGapList();

    const table = await screen.findByRole("table", { name: "Gaps by criticality" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("1")).toBeInTheDocument();
    expect(within(rows[0]).getByText("PR.AA-03")).toBeInTheDocument();
    expect(within(rows[0]).getByText("High")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Unauthorized access (Extreme)")).toBeInTheDocument();
    expect(within(rows[0]).getByText("System compromise (Extreme)")).toBeInTheDocument();
    expect(
      within(rows[0]).getByText("Authentication of administrator accounts governs privileged access.")
    ).toBeInTheDocument();
    expect(within(rows[0]).getByText("Based on version 1 · accepted agent result")).toBeInTheDocument();
    expect(within(rows[1]).getByText("PR.AA-01")).toBeInTheDocument();
    expect(getGapList).toHaveBeenCalledWith("org-1", "assessment-1", "token-1");
  });

  it("shows a gap without a rule as not classified, without inventing a priority", async () => {
    getGapList.mockResolvedValueOnce(gapList);

    renderGapList();

    const table = await screen.findByRole("table", { name: "Gaps by criticality" });
    const unclassified = within(table).getAllByRole("row")[2];
    expect(within(unclassified).getByText("Not classified")).toBeInTheDocument();
    expect(within(unclassified).getByText("—")).toBeInTheDocument();
    expect(within(unclassified).getByText("No classification rule for this control yet.")).toBeInTheDocument();
    expect(within(unclassified).queryByText(/High|Critical|Medium|Low/)).not.toBeInTheDocument();
  });

  it("says that the rules are provisional and how many controls are still pending review", async () => {
    getGapList.mockResolvedValueOnce(gapList);

    renderGapList();

    expect(
      await screen.findByText(
        "Priorities and risks follow Aligo's classification guide and are provisional until Aligo confirms them (rules 0.1)."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("1 control(s) still pending expert review are not included.")).toBeInTheDocument();
  });

  it("says so when there are no gaps and hides the provisional note when the rules are confirmed", async () => {
    getGapList.mockResolvedValueOnce({ ...gapList, gaps: [], pending_controls: 0, rules_provisional: false });

    renderGapList();

    expect(await screen.findByText("No gaps among the reviewed results.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText(/provisional/)).not.toBeInTheDocument();
    expect(screen.queryByText(/pending expert review/)).not.toBeInTheDocument();
  });

  it("shows an error with a retry, and loads the list again on retry", async () => {
    getGapList.mockRejectedValueOnce(Object.assign(new Error("Server error"), { status: 500 }));
    getGapList.mockResolvedValueOnce(gapList);

    renderGapList();

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Server error")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("table", { name: "Gaps by criticality" })).toBeInTheDocument();
    expect(getGapList).toHaveBeenCalledTimes(2);
  });

  it("asks the user to sign in again when the session has expired", async () => {
    getGapList.mockRejectedValueOnce(Object.assign(new Error("Unauthorized"), { status: 401 }));

    renderGapList();

    expect(await screen.findByText("Your session has expired. Sign in again to continue.")).toBeInTheDocument();
  });

  it("does not reload the list when only the access token is refreshed", async () => {
    getGapList.mockResolvedValue(gapList);

    const { rerender } = renderGapList();
    await screen.findByRole("table", { name: "Gaps by criticality" });

    rerender(<GapList organizationId="org-1" assessmentId="assessment-1" accessToken="token-2" />);
    await waitFor(() => expect(getGapList).toHaveBeenCalledTimes(1));

    // A different assessment loads its own list with the latest token.
    rerender(<GapList organizationId="org-1" assessmentId="assessment-2" accessToken="token-2" />);
    await waitFor(() => expect(getGapList).toHaveBeenCalledTimes(2));
    expect(getGapList).toHaveBeenLastCalledWith("org-1", "assessment-2", "token-2");
  });
});
