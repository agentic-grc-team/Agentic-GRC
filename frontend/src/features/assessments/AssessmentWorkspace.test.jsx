import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client.js";
import { listOrganizations } from "../organizations/api.js";
import { createAssessment, getAssessmentScope, listAssessments } from "./api.js";
import AssessmentWorkspace from "./AssessmentWorkspace.jsx";

vi.mock("../organizations/api.js", () => ({
  listOrganizations: vi.fn(),
}));

vi.mock("./api.js", () => ({
  listAssessments: vi.fn(),
  createAssessment: vi.fn(),
  getAssessmentScope: vi.fn(),
}));

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  promise.catch(() => {});
  return { promise, resolve, reject };
}

const organizations = [
  { id: "org-1", name: "Halverston Community Bank", role: "consultant" },
  { id: "org-2", name: "Beta Industries", role: "representative" },
];

function assessment(id, title, organizationId = "org-1") {
  return {
    id,
    organization_id: organizationId,
    title,
    framework_code: "NIST-CSF",
    framework_version: "2.0",
    kb_version: "demo-0.2",
    status: "in_progress",
    started_at: "2026-10-23T09:00:00Z",
  };
}

function scopeFor(item, organizationName = "Halverston Community Bank") {
  return {
    organization_id: item.organization_id,
    organization_name: organizationName,
    assessment: item,
    control_count: 1,
    functions: [
      {
        code: "PR",
        name: "Protect",
        categories: [
          {
            code: "PR.AA",
            name: "Identity Management, Authentication, and Access Control",
            controls: [{ code: "PR.AA-03", title: "Users, services, and hardware are authenticated" }],
          },
        ],
      },
    ],
  };
}

function renderWorkspace(props = {}) {
  return render(<AssessmentWorkspace accessToken="token-a" sessionId="user-a" {...props} />);
}

describe("AssessmentWorkspace", () => {
  beforeEach(() => {
    listOrganizations.mockResolvedValue(organizations);
    listAssessments.mockImplementation((organizationId) =>
      Promise.resolve(organizationId === "org-1" ? [assessment("assess-1", "Q3 baseline")] : []),
    );
    getAssessmentScope.mockImplementation((organizationId, assessmentId) =>
      Promise.resolve(scopeFor(assessment(assessmentId, "Q3 baseline", organizationId))),
    );
  });

  it("shows the scope of the first assessment of the selected organization", async () => {
    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "Q3 baseline" })).toBeInTheDocument();
    expect(listAssessments).toHaveBeenCalledWith("org-1", "token-a");
    expect(getAssessmentScope).toHaveBeenCalledWith("org-1", "assess-1", "token-a");
    expect(screen.getAllByText("Halverston Community Bank").length).toBeGreaterThan(0);
    expect(screen.getByText("PR.AA-03")).toBeInTheDocument();
    expect(screen.getByText("demo-0.2")).toBeInTheDocument();
  });

  it("starts with the organization chosen in another screen", async () => {
    renderWorkspace({ initialOrganizationId: "org-2" });

    expect(await screen.findByText("This organization has no assessments yet.")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Organization" })).toHaveValue("org-2");
    expect(listAssessments).toHaveBeenCalledWith("org-2", "token-a");
  });

  it("reports the selected organization to the app", async () => {
    const onOrganizationChange = vi.fn();
    renderWorkspace({ onOrganizationChange });

    await screen.findByRole("heading", { name: "Q3 baseline" });
    fireEvent.change(screen.getByRole("combobox", { name: "Organization" }), { target: { value: "org-2" } });

    await waitFor(() => expect(onOrganizationChange).toHaveBeenLastCalledWith("org-2"));
  });

  it("lets a consultant create an assessment and then shows its scope", async () => {
    const created = assessment("assess-2", "Q4 identity review");
    createAssessment.mockResolvedValue(created);
    renderWorkspace();
    await screen.findByRole("heading", { name: "Q3 baseline" });
    listAssessments.mockResolvedValue([created, assessment("assess-1", "Q3 baseline")]);
    getAssessmentScope.mockResolvedValue(scopeFor(created));

    fireEvent.change(screen.getByRole("textbox", { name: "New assessment title" }), {
      target: { value: "  Q4 identity review  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create assessment" }));

    expect(await screen.findByRole("heading", { name: "Q4 identity review" })).toBeInTheDocument();
    expect(createAssessment).toHaveBeenCalledWith("org-1", "Q4 identity review", "token-a");
    expect(getAssessmentScope).toHaveBeenLastCalledWith("org-1", "assess-2", "token-a");
    expect(screen.getByRole("combobox", { name: "Assessment" })).toHaveValue("assess-2");
    expect(screen.getByText(/"Q4 identity review" was created/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "New assessment title" })).toHaveValue("");

    getAssessmentScope.mockResolvedValue(scopeFor(assessment("assess-1", "Q3 baseline")));
    fireEvent.change(screen.getByRole("combobox", { name: "Assessment" }), { target: { value: "assess-1" } });

    expect(await screen.findByRole("heading", { name: "Q3 baseline" })).toBeInTheDocument();
    expect(screen.queryByText(/was created/)).not.toBeInTheDocument();
  });

  it("does not submit a blank title", async () => {
    renderWorkspace();
    await screen.findByRole("heading", { name: "Q3 baseline" });

    fireEvent.change(screen.getByRole("textbox", { name: "New assessment title" }), { target: { value: "   " } });

    expect(screen.getByRole("button", { name: "Create assessment" })).toBeDisabled();
    fireEvent.submit(screen.getByRole("button", { name: "Create assessment" }).closest("form"));
    expect(createAssessment).not.toHaveBeenCalled();
  });

  it("shows the backend message when creating fails", async () => {
    createAssessment.mockRejectedValue(
      new ApiError(403, { detail: "Only administrators and consultants can start an assessment." }),
    );
    renderWorkspace();
    await screen.findByRole("heading", { name: "Q3 baseline" });

    fireEvent.change(screen.getByRole("textbox", { name: "New assessment title" }), { target: { value: "Q4" } });
    fireEvent.click(screen.getByRole("button", { name: "Create assessment" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only administrators and consultants can start an assessment.",
    );
  });

  it("shows a readable validation message", async () => {
    createAssessment.mockRejectedValue(
      new ApiError(422, { detail: [{ msg: "Value error, This field cannot be blank." }] }),
    );
    renderWorkspace();
    await screen.findByRole("heading", { name: "Q3 baseline" });

    fireEvent.change(screen.getByRole("textbox", { name: "New assessment title" }), { target: { value: "Q4" } });
    fireEvent.click(screen.getByRole("button", { name: "Create assessment" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This field cannot be blank.");
  });

  it("lets a representative see the scope but not create an assessment", async () => {
    listAssessments.mockResolvedValue([assessment("assess-9", "Existing", "org-2")]);
    getAssessmentScope.mockResolvedValue(scopeFor(assessment("assess-9", "Existing", "org-2"), "Beta Industries"));
    renderWorkspace({ initialOrganizationId: "org-2" });

    expect(await screen.findByRole("heading", { name: "Existing" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "New assessment title" })).not.toBeInTheDocument();
    expect(screen.getByText(/An administrator or consultant creates assessments/)).toBeInTheDocument();
  });

  it("lets a platform administrator create in any listed organization", async () => {
    renderWorkspace({ isPlatformAdmin: true, initialOrganizationId: "org-2" });

    await screen.findByText("This organization has no assessments yet.");
    expect(screen.getByRole("textbox", { name: "New assessment title" })).toBeInTheDocument();
  });

  it("shows an access message and no scope when the assessment is not available", async () => {
    getAssessmentScope.mockRejectedValue(new ApiError(404, { detail: "Organization not found." }));
    renderWorkspace();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This assessment was not found, or you do not have access to it.",
    );
    expect(screen.queryByText("PR.AA-03")).not.toBeInTheDocument();
  });

  it("explains when the user has no organization", async () => {
    listOrganizations.mockResolvedValue([]);
    renderWorkspace();

    expect(await screen.findByText(/You are not a member of any organization yet/)).toBeInTheDocument();
    expect(listAssessments).not.toHaveBeenCalled();
  });

  it("ignores a late assessment list from the previously selected organization", async () => {
    const slowFirstList = deferred();
    listAssessments.mockImplementation((organizationId) =>
      organizationId === "org-1" ? slowFirstList.promise : Promise.resolve([assessment("assess-b", "Beta review", "org-2")]),
    );
    getAssessmentScope.mockImplementation((organizationId, assessmentId) =>
      Promise.resolve(scopeFor(assessment(assessmentId, "Beta review", organizationId), "Beta Industries")),
    );
    renderWorkspace();
    await waitFor(() => expect(listAssessments).toHaveBeenCalledWith("org-1", "token-a"));

    fireEvent.change(screen.getByRole("combobox", { name: "Organization" }), { target: { value: "org-2" } });
    expect(await screen.findByRole("heading", { name: "Beta review" })).toBeInTheDocument();

    await act(async () => {
      slowFirstList.resolve([assessment("assess-1", "Q3 baseline")]);
    });

    expect(screen.getByRole("heading", { name: "Beta review" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Assessment" })).toHaveValue("assess-b");
    expect(getAssessmentScope).not.toHaveBeenCalledWith("org-1", "assess-1", "token-a");
  });

  it("uses the refreshed token without reloading the screen", async () => {
    const { rerender } = renderWorkspace();
    await screen.findByRole("heading", { name: "Q3 baseline" });
    const callsBefore = listAssessments.mock.calls.length;

    rerender(<AssessmentWorkspace accessToken="token-b" sessionId="user-a" />);
    createAssessment.mockResolvedValue(assessment("assess-2", "After refresh"));
    fireEvent.change(screen.getByRole("textbox", { name: "New assessment title" }), { target: { value: "After refresh" } });
    fireEvent.click(screen.getByRole("button", { name: "Create assessment" }));

    await waitFor(() => expect(createAssessment).toHaveBeenCalledWith("org-1", "After refresh", "token-b"));
    await waitFor(() => expect(listAssessments.mock.calls.length).toBe(callsBefore + 1));
    expect(listAssessments).toHaveBeenLastCalledWith("org-1", "token-b");
    expect(listOrganizations).toHaveBeenCalledTimes(1);
  });
});
