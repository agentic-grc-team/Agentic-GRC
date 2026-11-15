import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import GapList from "./GapList.jsx";

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

function renderGapList(list = gapList) {
  return render(<GapList gapList={list} />);
}

describe("GapList", () => {
  it("lists the gaps in the order the API returns them, with their classification", async () => {
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
  });

  it("shows a gap without a rule as not classified, without inventing a priority", async () => {
    renderGapList();

    const table = await screen.findByRole("table", { name: "Gaps by criticality" });
    const unclassified = within(table).getAllByRole("row")[2];
    expect(within(unclassified).getByText("Not classified")).toBeInTheDocument();
    expect(within(unclassified).getByText("—")).toBeInTheDocument();
    expect(within(unclassified).getByText("No classification rule for this control yet.")).toBeInTheDocument();
    expect(within(unclassified).queryByText(/High|Critical|Medium|Low/)).not.toBeInTheDocument();
  });

  it("says that the rules are provisional and how many controls have no final result yet", async () => {
    renderGapList();

    expect(
      await screen.findByText(
        "Priorities and risks follow Aligo's classification guide and are provisional until Aligo confirms them (rules 0.1)."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("1 control(s) without a final reviewed result yet are not included.")).toBeInTheDocument();
  });

  it("says so when there are no gaps and hides the provisional note when the rules are confirmed", async () => {
    renderGapList({ ...gapList, gaps: [], pending_controls: 0, rules_provisional: false });

    expect(await screen.findByText("No gaps among the reviewed results.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText(/provisional/)).not.toBeInTheDocument();
    expect(screen.queryByText(/without a final reviewed result/)).not.toBeInTheDocument();
  });

  it("renders nothing without a gap list", () => {
    const { container } = render(<GapList gapList={undefined} />);

    expect(container).toBeEmptyDOMElement();
  });
});
