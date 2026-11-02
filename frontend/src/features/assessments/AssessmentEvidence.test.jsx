import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client.js";
import {
  linkEvidence,
  listAssessmentControls,
  listAssessmentEvidence,
  listEvidenceLinks,
  unlinkEvidence,
} from "./api.js";
import AssessmentEvidence from "./AssessmentEvidence.jsx";

vi.mock("../organizations/EvidenceUpload.jsx", () => ({
  default: ({ organizationId, assessmentId, onUploaded }) => (
    <button type="button" onClick={() => onUploaded({ id: "new" })}>
      {`Upload to ${organizationId}:${assessmentId}`}
    </button>
  ),
}));

vi.mock("./api.js", () => ({
  linkEvidence: vi.fn(),
  listAssessmentControls: vi.fn(),
  listAssessmentEvidence: vi.fn(),
  listEvidenceLinks: vi.fn(),
  unlinkEvidence: vi.fn(),
}));

const controls = [
  { id: "control-1", code: "PR.AA-01", title: "Identities are managed" },
  { id: "control-3", code: "PR.AA-03", title: "Users are authenticated" },
];

const policy = { id: "file-1", original_filename: "MFA-policy.pdf" };
const report = { id: "file-2", original_filename: "access-report.xlsx" };

function link(id, evidenceId, controlId) {
  return { id, evidence_file_id: evidenceId, assessment_control_id: controlId };
}

function renderEvidence(props = {}) {
  return render(
    <AssessmentEvidence
      organizationId="org-1"
      assessmentId="assess-1"
      accessToken="token-a"
      sessionId="user-a"
      {...props}
    />,
  );
}

function attachedPolicy() {
  return screen.findByRole("button", { name: "Remove MFA-policy.pdf from PR.AA-03" });
}

function controlRow(code) {
  return screen.getByText(code).closest("li");
}

describe("AssessmentEvidence", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    listAssessmentControls.mockResolvedValue(controls);
    listAssessmentEvidence.mockResolvedValue([policy, report]);
    listEvidenceLinks.mockResolvedValue([link("link-1", "file-1", "control-3")]);
  });

  it("shows the documents attached to each control", async () => {
    renderEvidence();

    await attachedPolicy();
    expect(listAssessmentControls).toHaveBeenCalledWith("org-1", "assess-1", "token-a");
    expect(listAssessmentEvidence).toHaveBeenCalledWith("org-1", "assess-1", "token-a");
    expect(listEvidenceLinks).toHaveBeenCalledWith("org-1", "assess-1", "token-a");

    expect(
      within(screen.getByRole("list", { name: "Documents attached to PR.AA-03" })).getByText("MFA-policy.pdf"),
    ).toBeInTheDocument();
    expect(within(controlRow("PR.AA-01")).getByText("No documents attached.")).toBeInTheDocument();
  });

  it("only offers documents that are not attached yet", async () => {
    renderEvidence();

    await attachedPolicy();

    const options = within(screen.getByLabelText("Attach a document to PR.AA-03"))
      .getAllByRole("option")
      .map((option) => option.textContent);
    expect(options).toEqual(["Choose a document", "access-report.xlsx"]);
  });

  it("attaches a document to a control", async () => {
    linkEvidence.mockResolvedValue(link("link-2", "file-2", "control-1"));
    renderEvidence();

    await attachedPolicy();
    fireEvent.change(screen.getByLabelText("Attach a document to PR.AA-01"), {
      target: { value: "file-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Attach to PR.AA-01" }));

    await waitFor(() =>
      expect(
        within(screen.getByRole("list", { name: "Documents attached to PR.AA-01" })).getByText("access-report.xlsx"),
      ).toBeInTheDocument(),
    );
    expect(linkEvidence).toHaveBeenCalledWith("org-1", "file-2", "control-1", "token-a");
  });

  it("removes a document from a control", async () => {
    unlinkEvidence.mockResolvedValue(null);
    renderEvidence();

    await attachedPolicy();
    fireEvent.click(screen.getByRole("button", { name: "Remove MFA-policy.pdf from PR.AA-03" }));

    await waitFor(() =>
      expect(within(controlRow("PR.AA-03")).getByText("No documents attached.")).toBeInTheDocument(),
    );
    expect(unlinkEvidence).toHaveBeenCalledWith("org-1", "file-1", "control-3", "token-a");
  });

  it("keeps the current state and shows the reason when attaching fails", async () => {
    linkEvidence.mockRejectedValue(
      new ApiError(409, { detail: "Evidence file belongs to a different assessment." }),
    );
    renderEvidence();

    await attachedPolicy();
    fireEvent.change(screen.getByLabelText("Attach a document to PR.AA-01"), {
      target: { value: "file-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Attach to PR.AA-01" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Evidence file belongs to a different assessment.",
    );
    expect(within(controlRow("PR.AA-01")).getByText("No documents attached.")).toBeInTheDocument();
  });

  it("reloads the lists after an upload", async () => {
    renderEvidence();

    await attachedPolicy();
    expect(listAssessmentEvidence).toHaveBeenCalledTimes(1);

    listAssessmentEvidence.mockResolvedValue([policy, report, { id: "file-3", original_filename: "new.txt" }]);
    fireEvent.click(screen.getByRole("button", { name: "Upload to org-1:assess-1" }));

    await waitFor(() => expect(listAssessmentEvidence).toHaveBeenCalledTimes(2));
    fireEvent.change(await screen.findByLabelText("Attach a document to PR.AA-01"), {
      target: { value: "file-3" },
    });
    expect(screen.getByLabelText("Attach a document to PR.AA-01")).toHaveValue("file-3");
  });

  it("explains that nothing is attached when no document was uploaded yet", async () => {
    listAssessmentEvidence.mockResolvedValue([]);
    listEvidenceLinks.mockResolvedValue([]);
    renderEvidence();

    expect(await screen.findByText("Upload a document above to attach it to a control.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Attach a document to PR.AA-01")).not.toBeInTheDocument();
  });

  it("says loading failed instead of showing empty lists, and can retry", async () => {
    listAssessmentControls.mockRejectedValueOnce(new ApiError(500, {}));
    renderEvidence();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("No documents attached.")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry loading evidence" }));

    await attachedPolicy();
  });
});
