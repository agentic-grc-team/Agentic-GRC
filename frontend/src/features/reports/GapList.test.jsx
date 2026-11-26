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
  remediation_rules_id: "rule:remediation",
  remediation_rules_version: "0.1",
  remediation_rules_provisional: true,
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
      evidence: [],
      linked_evidence: [],
      evidence_absent: true,
      remediation: {
        statement: "Authentication of privileged accounts",
        issue: "Administrator accounts that sign in with a password alone can be taken over.",
        requirement: "Every administrator account must use a second authentication factor.",
        task: "Enforce multi-factor authentication for all administrator accounts",
        task_description:
          "Identify every privileged account and enforce a second factor for all of them.",
        how_to: [
          "List every administrator account.",
          "Register a second factor.",
          "Enforce it centrally.",
        ],
        dependency: "Technology",
        time_horizon: "Short term",
        evidence_to_close: ["Conditional access policy", "Authentication methods report"],
        justification: "PR.AA-03 was assessed as not implemented (question IAM-01).",
      },
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
      evidence: [
        { source_type: "interview_turn", reference: "Interview turn 4", nature: "attestation" },
      ],
      linked_evidence: [
        {
          id: "file-1",
          file_name: "leavers-procedure.pdf",
          file_type: "PDF",
          size_bytes: 2048,
          sha256: "a".repeat(64),
          uploaded_at: "2026-11-14T09:00:00Z",
          linked_at: "2026-11-14T10:00:00Z",
          added_after_review: false,
          verification: "not_verified",
          verification_label: "Not verified",
        },
      ],
      evidence_absent: false,
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
      within(rows[0]).getByText(
        "Authentication of administrator accounts governs privileged access.",
      ),
    ).toBeInTheDocument();
    expect(
      within(rows[0]).getByText("Based on version 1 · accepted agent result"),
    ).toBeInTheDocument();
    expect(within(rows[1]).getByText("PR.AA-01")).toBeInTheDocument();
  });

  it("shows a gap without a rule as not classified, without inventing a priority", async () => {
    renderGapList();

    const table = await screen.findByRole("table", { name: "Gaps by criticality" });
    const unclassified = within(table).getAllByRole("row")[2];
    expect(within(unclassified).getByText("Not classified")).toBeInTheDocument();
    expect(within(unclassified).getByText("—")).toBeInTheDocument();
    expect(
      within(unclassified).getByText("No classification rule for this control yet."),
    ).toBeInTheDocument();
    expect(within(unclassified).queryByText(/High|Critical|Medium|Low/)).not.toBeInTheDocument();
  });

  it("shows each gap's evidence, or says plainly that there is none (HU-16)", async () => {
    renderGapList();

    const table = await screen.findByRole("table", { name: "Gaps by criticality" });
    const [, withoutEvidence, withEvidence] = within(table).getAllByRole("row");
    expect(within(withoutEvidence).getByText("No evidence")).toBeInTheDocument();
    expect(within(withEvidence).getByText("leavers-procedure.pdf")).toBeInTheDocument();
    expect(within(withEvidence).getByText("PDF · Not verified")).toBeInTheDocument();
    expect(within(withEvidence).queryByText(/Added after the review/)).not.toBeInTheDocument();
    expect(within(withEvidence).getByText("Interview turn 4")).toBeInTheDocument();
    expect(within(withEvidence).queryByText("No evidence")).not.toBeInTheDocument();
  });

  it("marks a file linked after the review and does not present it as supporting evidence", async () => {
    const [first, second] = gapList.gaps;
    const lateFile = { ...second.linked_evidence[0], added_after_review: true };
    renderGapList({
      ...gapList,
      gaps: [
        first,
        { ...second, evidence: [], linked_evidence: [lateFile], evidence_absent: true },
      ],
    });

    const table = await screen.findByRole("table", { name: "Gaps by criticality" });
    const row = within(table).getAllByRole("row")[2];
    expect(within(row).getByText("No evidence at the time of the review")).toBeInTheDocument();
    expect(within(row).getByText("leavers-procedure.pdf")).toBeInTheDocument();
    expect(
      within(row).getByText("PDF · Not verified · Added after the review"),
    ).toBeInTheDocument();
  });

  it("says that the rules are provisional and how many controls have no final result yet", async () => {
    renderGapList();

    expect(
      await screen.findByText(
        "Priorities and risks follow Aligo's classification guide and are provisional until Aligo confirms them (rules 0.1).",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("1 control(s) without a final reviewed result yet are not included."),
    ).toBeInTheDocument();
  });

  it("says so when there are no gaps and hides the provisional note when the rules are confirmed", async () => {
    renderGapList({ ...gapList, gaps: [], pending_controls: 0, rules_provisional: false });

    expect(await screen.findByText("No gaps among the reviewed results.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText(/provisional/)).not.toBeInTheDocument();
    expect(screen.queryByText(/without a final reviewed result/)).not.toBeInTheDocument();
  });

  it("lists a remediation recommendation for each gap, with steps and the reason behind it (HU-18)", async () => {
    renderGapList();

    const plan = await screen.findByRole("list", { name: "Remediation recommendations" });
    const [withRecommendation, withoutRecommendation] = within(plan).getAllByRole("listitem", {
      name: (_, element) => element.parentElement === plan,
    });
    expect(within(withRecommendation).getByText("PR.AA-03")).toBeInTheDocument();
    expect(
      within(withRecommendation).getByText(
        "Recommendation: Enforce multi-factor authentication for all administrator accounts",
      ),
    ).toBeInTheDocument();
    expect(within(withRecommendation).getByText("Short term · Technology")).toBeInTheDocument();
    const steps = within(withRecommendation).getByRole("list", { name: "Steps for PR.AA-03" });
    expect(
      within(steps)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "List every administrator account.",
      "Register a second factor.",
      "Enforce it centrally.",
    ]);
    expect(
      within(withRecommendation).getByText(
        "Evidence that closes the gap: Conditional access policy; Authentication methods report",
      ),
    ).toBeInTheDocument();
    expect(
      within(withRecommendation).getByText(
        "Why: PR.AA-03 was assessed as not implemented (question IAM-01).",
      ),
    ).toBeInTheDocument();
    // The unclassified gap gets no invented recommendation.
    expect(within(withoutRecommendation).getByText("PR.AA-01")).toBeInTheDocument();
    expect(
      within(withoutRecommendation).getByText(
        "No remediation recommendation without a classification.",
      ),
    ).toBeInTheDocument();
  });

  it("says when a classified gap has no recommendation and that recommendations are provisional", async () => {
    const [first, second] = gapList.gaps;
    renderGapList({ ...gapList, gaps: [{ ...first, remediation: null }, second] });

    expect(
      await screen.findByText("No remediation recommendation for this control yet."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Remediation recommendations are provisional templates until Aligo confirms them/,
      ),
    ).toBeInTheDocument();
  });

  it("renders nothing without a gap list", () => {
    const { container } = render(<GapList gapList={undefined} />);

    expect(container).toBeEmptyDOMElement();
  });
});
