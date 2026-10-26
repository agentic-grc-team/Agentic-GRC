import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AssessmentScope from "./AssessmentScope.jsx";

const scope = {
  organization_id: "org-1",
  organization_name: "Halverston Community Bank",
  assessment: {
    id: "assess-1",
    organization_id: "org-1",
    title: "Q4 identity review",
    framework_code: "NIST-CSF",
    framework_version: "2.0",
    kb_version: "demo-0.2",
    status: "in_progress",
    started_at: "2026-10-23T09:00:00Z",
  },
  control_count: 3,
  functions: [
    {
      code: "PR",
      name: "Protect",
      categories: [
        {
          code: "PR.AA",
          name: "Identity Management, Authentication, and Access Control",
          controls: [
            { code: "PR.AA-01", title: "Identities and credentials are managed" },
            { code: "PR.AA-03", title: "Users, services, and hardware are authenticated" },
            { code: "PR.AA-05", title: "Access permissions are defined in a policy" },
          ],
        },
      ],
    },
  ],
};

describe("AssessmentScope", () => {
  it("shows the organization, framework, knowledge base and start date", () => {
    render(<AssessmentScope scope={scope} />);

    expect(screen.getByRole("heading", { name: "Q4 identity review" })).toBeInTheDocument();
    expect(screen.getByText("Halverston Community Bank")).toBeInTheDocument();
    expect(screen.getByText("NIST CSF 2.0")).toBeInTheDocument();
    expect(screen.getByText("demo-0.2")).toBeInTheDocument();
    expect(screen.getByText("2026-10-23")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
  });

  it("lists only the in-scope controls grouped by function and category", () => {
    render(<AssessmentScope scope={scope} />);

    expect(screen.getByText(/3 controls in 1 category and 1 function\./)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Protect (PR)" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "PR.AA · Identity Management, Authentication, and Access Control" }),
    ).toBeInTheDocument();
    const controls = within(screen.getByRole("list", { name: "Controls in PR.AA" })).getAllByRole("listitem");
    expect(controls.map((item) => item.textContent)).toEqual([
      "PR.AA-01Identities and credentials are managed",
      "PR.AA-03Users, services, and hardware are authenticated",
      "PR.AA-05Access permissions are defined in a policy",
    ]);
  });

  it("shows only the code for a category without a catalog name", () => {
    const unnamed = {
      ...scope,
      control_count: 1,
      functions: [
        {
          code: "PR",
          name: "Protect",
          categories: [{ code: "PR.ZZ", name: null, controls: [{ code: "PR.ZZ-01", title: "Unknown" }] }],
        },
      ],
    };

    render(<AssessmentScope scope={unnamed} />);

    expect(screen.getByRole("heading", { name: "PR.ZZ" })).toBeInTheDocument();
    expect(screen.getByText(/1 control in 1 category and 1 function\./)).toBeInTheDocument();
  });

  it("says clearly when nothing is in scope", () => {
    render(<AssessmentScope scope={{ ...scope, control_count: 0, functions: [] }} />);

    expect(screen.getByRole("alert")).toHaveTextContent("No controls are in scope for this assessment");
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("shows a missing start date as not started", () => {
    render(<AssessmentScope scope={{ ...scope, assessment: { ...scope.assessment, started_at: null } }} />);

    expect(screen.getByText("Not started")).toBeInTheDocument();
  });

  it("does not break on an unreadable start date", () => {
    render(<AssessmentScope scope={{ ...scope, assessment: { ...scope.assessment, started_at: "not-a-date" } }} />);

    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Q4 identity review" })).toBeInTheDocument();
  });
});
