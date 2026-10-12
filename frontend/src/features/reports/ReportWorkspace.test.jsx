import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listOrganizations } from "../organizations/api.js";
import { DEMO_ASSESSMENT_ID, downloadReportPdf, getReportPreview } from "./api.js";
import ReportWorkspace from "./ReportWorkspace.jsx";

vi.mock("./api.js", async (importOriginal) => ({
  ...(await importOriginal()),
  getReportPreview: vi.fn(),
  downloadReportPdf: vi.fn(),
}));

vi.mock("../organizations/api.js", () => ({
  listOrganizations: vi.fn(),
}));

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const mockOrganizations = [
  {
    id: "org-1",
    name: "Acme Corp",
    sector: "Financial services",
    size: "51-250 employees",
    role: "member",
  },
  {
    id: "org-2",
    name: "Beta Industries",
    sector: "Healthcare",
    size: "250-500 employees",
    role: "administrator",
  },
];

const mockReportView = {
  organization: {
    id: "org-1",
    name: "Acme Corp",
    sector: "Financial services",
    size: "51-250 employees",
  },
  assessment: {
    id: DEMO_ASSESSMENT_ID,
    title: "Identity and access — demo assessment",
    framework: "NIST CSF 2.0",
    kb_version: "kb-demo-0.1",
    status: "awaiting_review",
    started_at: "2026-01-15T09:00:00Z",
    completed_at: null,
  },
  generated_at: "2026-10-12T19:00:00Z",
  is_demo_data: true,
  scope: [
    { code: "PR.AA-01", title: "Identity management" },
    { code: "PR.AA-03", title: "Authentication" },
    { code: "PR.AA-05", title: "Access permissions" },
    { code: "ID.AM-01", title: "Hardware inventory" },
    { code: "PR.PS-06", title: "Secure development" },
    { code: "DE.CM-01", title: "Network monitoring" },
  ],
  results: [
    {
      code: "PR.AA-01",
      title: "Identity management",
      control_status: "implemented",
      status_label: "Implemented",
      basis: "accepted_agent_result",
      reviewed_by: "Consultant Alice",
      reviewed_at: "2026-01-17T10:00:00Z",
      explanation: "Full identity governance.",
      not_assessed_reason: null,
      evidence: [
        {
          source_type: "tenant_configuration",
          reference: "Okta Config",
          excerpt: "Automated provisioning",
          nature: "implementation",
        },
      ],
      evidence_pending: false,
    },
    {
      code: "PR.AA-03",
      title: "Authentication",
      control_status: "partially_implemented",
      status_label: "Partially implemented",
      basis: "consultant_version",
      reviewed_by: "Aligo Consultant (demo)",
      reviewed_at: "2026-01-17T12:00:00Z",
      explanation: "MFA partial across legacy systems.",
      not_assessed_reason: null,
      evidence: [],
      evidence_pending: false,
    },
  ],
  pending: [
    {
      code: "PR.AA-05",
      title: "Access permissions",
      reason: "awaiting_review",
      reason_label: "Awaiting expert review",
    },
    {
      code: "ID.AM-01",
      title: "Hardware inventory",
      reason: "rejected_awaiting_new_version",
      reason_label: "Rejected by reviewer — new assessment required",
    },
    {
      code: "DE.CM-01",
      title: "Network monitoring",
      reason: "no_result",
      reason_label: "Not yet assessed",
    },
  ],
  exclusions: [
    {
      code: "PR.PS-06",
      title: "Secure software development",
      justification: "Organization does not develop software in-house.",
      reviewed_by: "Aligo Consultant (demo)",
      reviewed_at: "2026-01-17T14:00:00Z",
    },
  ],
  summary: {
    controls_in_scope: 6,
    finalized: 3,
    pending: 3,
    coverage_pct: 50.0,
    status_counts: {
      implemented: 1,
      partially_implemented: 1,
      not_implemented: 0,
      not_assessed: 0,
    },
  },
};

describe("ReportWorkspace", () => {
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;

  beforeEach(() => {
    vi.clearAllMocks();
    listOrganizations.mockResolvedValue(mockOrganizations);
    getReportPreview.mockResolvedValue(mockReportView);
  });

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    vi.restoreAllMocks();
  });

  it("loads organizations, then requests the preview for the first organization with DEMO_ASSESSMENT_ID and the token", async () => {
    render(<ReportWorkspace accessToken="test-bearer-token" />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading report preview…");

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    expect(listOrganizations).toHaveBeenCalledWith("test-bearer-token");
    expect(getReportPreview).toHaveBeenCalledWith(
      "org-1",
      DEMO_ASSESSMENT_ID,
      "test-bearer-token"
    );
  });

  it("renders the summary tiles with the right numbers, including '50.0%'", async () => {
    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const summary = screen.getByText("Controls in scope").closest("dl");
    expect(within(summary).getByText("Controls in scope").parentElement).toHaveTextContent("6");
    expect(within(summary).getByText("Final results").parentElement).toHaveTextContent("2");
    expect(within(summary).getByText("Pending review").parentElement).toHaveTextContent("3");
    expect(within(summary).getByText("Exclusions").parentElement).toHaveTextContent("1");
    expect(within(summary).getByText("Coverage").parentElement).toHaveTextContent("50.0%");
  });

  it("reviewed results table contains 'Partially implemented' and the reviewer with the date", async () => {
    render(<ReportWorkspace accessToken="test-token" />);

    const table = await screen.findByRole("table", { name: "Reviewed results" });
    expect(within(table).getByText("Partially implemented")).toBeInTheDocument();
    expect(
      within(table).getByText("Aligo Consultant (demo) · 2026-01-17")
    ).toBeInTheDocument();
  });

  it("a pending control appears in the 'Pending review' table and not in the 'Reviewed results' table", async () => {
    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const reviewedTable = screen.getByRole("table", { name: "Reviewed results" });
    const pendingTable = screen.getByRole("table", { name: "Pending review" });

    expect(within(pendingTable).getByText("PR.AA-05")).toBeInTheDocument();
    expect(within(reviewedTable).queryByText("PR.AA-05")).not.toBeInTheDocument();
  });

  it("exclusion row shows its justification", async () => {
    render(<ReportWorkspace accessToken="test-token" />);

    const exclusionsTable = await screen.findByRole("table", { name: "Exclusions" });
    expect(within(exclusionsTable).getByText("PR.PS-06")).toBeInTheDocument();
    expect(
      within(exclusionsTable).getByText("Organization does not develop software in-house.")
    ).toBeInTheDocument();
  });

  it("shows the 'Demo data' badge and the pending notice", async () => {
    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    expect(screen.getByText("Demo data")).toHaveClass("report-badge");
    expect(
      screen.getByText(/3 control\(s\) pending expert review/)
    ).toHaveClass("report-notice");
  });

  it("assessment status shows 'Awaiting review' (label), not awaiting_review", async () => {
    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    expect(screen.getByText(/Status: Awaiting review/)).toBeInTheDocument();
    expect(screen.queryByText(/Status: awaiting_review/)).not.toBeInTheDocument();
  });

  it("with 2 organizations, changing the select requests the preview for the second org", async () => {
    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const select = screen.getByLabelText("Organization");
    expect(select).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "org-2" } });

    expect(getReportPreview).toHaveBeenCalledWith(
      "org-2",
      DEMO_ASSESSMENT_ID,
      "test-token"
    );
  });

  it("stale response: preview for org A resolves after the user switched to org B -> only org B's data is displayed", async () => {
    const previewA = deferred();
    const previewB = deferred();

    getReportPreview.mockImplementation((orgId) => {
      if (orgId === "org-1") return previewA.promise;
      if (orgId === "org-2") return previewB.promise;
      return Promise.reject(new Error("Unknown org"));
    });

    render(<ReportWorkspace accessToken="test-token" />);

    // Switch to org-2 while org-1 is still loading
    const select = await screen.findByLabelText("Organization");
    fireEvent.change(select, { target: { value: "org-2" } });

    // Org B resolves
    previewB.resolve({
      ...mockReportView,
      assessment: {
        ...mockReportView.assessment,
        title: "Org B Assessment Title",
      },
    });

    await screen.findByRole("heading", { name: "Org B Assessment Title" });

    // Org A resolves late; flush its handlers so a missing guard would re-render
    await act(async () => {
      previewA.resolve({
        ...mockReportView,
        assessment: {
          ...mockReportView.assessment,
          title: "Org A Assessment Title",
        },
      });
    });

    // Make sure Org B is displayed and Org A is never displayed
    expect(
      screen.getByRole("heading", { name: "Org B Assessment Title" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Org A Assessment Title" })
    ).not.toBeInTheDocument();
  });

  it("empty organizations -> empty-state text and getReportPreview not called", async () => {
    listOrganizations.mockResolvedValueOnce([]);

    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByText(
      "You are not a member of any organization yet. Ask your administrator for an invitation."
    );

    expect(getReportPreview).not.toHaveBeenCalled();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("organizations request fails -> shows the error, not the empty state, and retries", async () => {
    listOrganizations.mockRejectedValueOnce({ status: 401, message: "Could not validate credentials." });

    render(<ReportWorkspace accessToken="test-token" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Your session has expired. Sign in again to continue.");
    expect(
      screen.queryByText(/You are not a member of any organization yet/)
    ).not.toBeInTheDocument();
    expect(getReportPreview).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });
    expect(listOrganizations).toHaveBeenCalledTimes(2);
  });

  it("preview 404 -> shows 'No report is available for this organization yet.'; clicking 'Try again' calls getReportPreview again", async () => {
    getReportPreview.mockRejectedValueOnce({
      status: 404,
      message: "Assessment not found.",
    });

    render(<ReportWorkspace accessToken="test-token" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No report is available for this organization yet.");

    getReportPreview.mockResolvedValueOnce(mockReportView);
    const tryAgainBtn = screen.getByRole("button", { name: "Try again" });
    fireEvent.click(tryAgainBtn);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });
    expect(getReportPreview).toHaveBeenCalledTimes(2);
  });

  it("preview 401 -> session-expired message", async () => {
    getReportPreview.mockRejectedValueOnce({
      status: 401,
      message: "Could not validate credentials.",
    });

    render(<ReportWorkspace accessToken="test-token" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Your session has expired. Sign in again to continue."
    );
  });

  it("download success handles blob, anchor click, revokeObjectURL, and success status", async () => {
    URL.createObjectURL = vi.fn(() => "blob:test");
    URL.revokeObjectURL = vi.fn();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const downloadDeferred = deferred();
    downloadReportPdf.mockReturnValueOnce(downloadDeferred.promise);

    render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const downloadBtn = screen.getByRole("button", { name: "Download PDF" });
    fireEvent.click(downloadBtn);

    expect(downloadBtn).toBeDisabled();
    expect(downloadBtn).toHaveTextContent("Preparing PDF…");

    downloadDeferred.resolve({
      blob: new Blob(["%PDF-1.4 demo"]),
      filename: "agentic-grc-report-x.pdf",
    });

    await screen.findByText("Report downloaded.");
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test");
    expect(downloadBtn).not.toBeDisabled();
    expect(downloadBtn).toHaveTextContent("Download PDF");
  });

  it("download failure shows alert with the 404 message and preview remains visible", async () => {
    downloadReportPdf.mockRejectedValueOnce({
      status: 404,
      message: "Assessment not found.",
    });

    render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const downloadBtn = screen.getByRole("button", { name: "Download PDF" });
    fireEvent.click(downloadBtn);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No report is available for this organization yet.");
    expect(
      screen.getByRole("heading", { name: "Identity and access — demo assessment" })
    ).toBeInTheDocument();
  });
});
