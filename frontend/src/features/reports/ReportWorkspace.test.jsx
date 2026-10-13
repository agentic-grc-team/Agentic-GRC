import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listAssessments } from "../assessments/api.js";
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

vi.mock("../assessments/api.js", () => ({
  listAssessments: vi.fn(),
}));

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  promise.catch(() => {});
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
    final_with_evidence_pending: 0,
    status_counts: {
      implemented: 1,
      partially_implemented: 1,
      not_implemented: 0,
      not_assessed: 0,
    },
  },
};

const mockReportViewWithEvidencePending = {
  ...mockReportView,
  results: [
    {
      ...mockReportView.results[0],
      evidence_pending: true,
    },
    {
      ...mockReportView.results[1],
      evidence_pending: false,
    },
  ],
  summary: {
    ...mockReportView.summary,
    final_with_evidence_pending: 1,
  },
};

const mockAssessments = [
  {
    id: "assess-1",
    title: "Identity and access",
    status: "in_progress",
    started_at: "2026-10-13T09:00:00Z",
  },
];

describe("ReportWorkspace", () => {
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;

  beforeEach(() => {
    vi.clearAllMocks();
    listOrganizations.mockReset();
    listAssessments.mockReset();
    getReportPreview.mockReset();
    downloadReportPdf.mockReset();
    listOrganizations.mockResolvedValue(mockOrganizations);
    listAssessments.mockResolvedValue(mockAssessments);
    getReportPreview.mockResolvedValue(mockReportView);
  });

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    vi.restoreAllMocks();
  });

  it("loads organizations, then requests the preview for the first organization with assess-1 and the token", async () => {
    render(<ReportWorkspace accessToken="test-bearer-token" />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading report preview…");

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    expect(listOrganizations).toHaveBeenCalledWith("test-bearer-token");
    expect(listAssessments).toHaveBeenCalledWith("org-1", "test-bearer-token");
    expect(getReportPreview).toHaveBeenCalledWith(
      "org-1",
      "assess-1",
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

    await waitFor(() => {
      expect(getReportPreview).toHaveBeenCalledWith(
        "org-2",
        "assess-1",
        "test-token"
      );
    });
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
    await waitFor(() => {
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test");
    });
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
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

  it("token change clears the old screen while new session organizations are pending", async () => {
    const { rerender } = render(<ReportWorkspace accessToken="token-1" />);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("Controls in scope")).toBeInTheDocument();
    expect(screen.getAllByRole("table").length).toBeGreaterThan(0);

    const orgsPending = deferred();
    listOrganizations.mockReturnValueOnce(orgsPending.promise);

    rerender(<ReportWorkspace accessToken="token-2" />);

    expect(screen.queryByText("Acme Corp")).not.toBeInTheDocument();
    expect(screen.queryByText("Controls in scope")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(listOrganizations).toHaveBeenCalledWith("token-2");
  });

  it("old preview after token change is ignored", async () => {
    const preview1 = deferred();
    getReportPreview.mockReturnValueOnce(preview1.promise);

    const { rerender } = render(<ReportWorkspace accessToken="token-1" />);

    await waitFor(() => {
      expect(getReportPreview).toHaveBeenCalledWith("org-1", "assess-1", "token-1");
    });

    const token2Orgs = [
      {
        id: "org-2",
        name: "Beta Industries",
        sector: "Healthcare",
        size: "250-500 employees",
        role: "administrator",
      },
    ];
    const preview2 = {
      ...mockReportView,
      organization: {
        id: "org-2",
        name: "Beta Industries",
        sector: "Healthcare",
        size: "250-500 employees",
      },
      assessment: {
        ...mockReportView.assessment,
        title: "Beta Assessment Title",
      },
    };

    const token2OrgsPending = deferred();
    listOrganizations.mockReturnValueOnce(token2OrgsPending.promise);
    getReportPreview.mockResolvedValueOnce(preview2);

    rerender(<ReportWorkspace accessToken="token-2" />);

    // The old response arrives while the new session's organizations are still loading: no newer
    // preview request exists yet, so only the invalidation on token change can keep it off screen.
    await act(async () => {
      preview1.resolve({
        ...mockReportView,
        assessment: {
          ...mockReportView.assessment,
          title: "Old Token-1 Assessment Title",
        },
      });
    });

    expect(
      screen.queryByRole("heading", { name: "Old Token-1 Assessment Title" })
    ).not.toBeInTheDocument();

    await act(async () => {
      token2OrgsPending.resolve(token2Orgs);
    });

    await screen.findByRole("heading", { name: "Beta Assessment Title" });
    expect(screen.getByText(/Beta Industries/)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Old Token-1 Assessment Title" })
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Acme Corp")).not.toBeInTheDocument();
  });

  it("new session with no organizations ignores old preview response", async () => {
    const preview1 = deferred();
    getReportPreview.mockReturnValueOnce(preview1.promise);

    const { rerender } = render(<ReportWorkspace accessToken="token-1" />);

    await waitFor(() => {
      expect(getReportPreview).toHaveBeenCalledWith("org-1", "assess-1", "token-1");
    });

    listOrganizations.mockResolvedValueOnce([]);
    rerender(<ReportWorkspace accessToken="token-2" />);

    await screen.findByText(
      "You are not a member of any organization yet. Ask your administrator for an invitation."
    );

    await act(async () => {
      preview1.resolve(mockReportView);
    });

    expect(
      screen.getByText(
        "You are not a member of any organization yet. Ask your administrator for an invitation."
      )
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Identity and access — demo assessment" })
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("new session whose organizations request fails keeps error alert and ignores old preview", async () => {
    const preview1 = deferred();
    getReportPreview.mockReturnValueOnce(preview1.promise);

    const { rerender } = render(<ReportWorkspace accessToken="token-1" />);

    await waitFor(() => {
      expect(getReportPreview).toHaveBeenCalledWith("org-1", "assess-1", "token-1");
    });

    listOrganizations.mockRejectedValueOnce({ status: 401, message: "Unauthorized" });
    rerender(<ReportWorkspace accessToken="token-2" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Your session has expired. Sign in again to continue.");

    await act(async () => {
      preview1.resolve(mockReportView);
    });

    expect(alert).toHaveTextContent("Your session has expired. Sign in again to continue.");
    expect(
      screen.queryByRole("heading", { name: "Identity and access — demo assessment" })
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("switching organization during a pending download invalidates the download", async () => {
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

    const select = screen.getByLabelText("Organization");
    fireEvent.change(select, { target: { value: "org-2" } });

    await act(async () => {
      downloadDeferred.resolve({
        blob: new Blob(["%PDF-1.4 demo"]),
        filename: "agentic-grc-report-org1.pdf",
      });
    });

    expect(clickSpy).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(screen.queryByText("Report downloaded.")).not.toBeInTheDocument();

    const currentDownloadBtn = await screen.findByRole("button", { name: "Download PDF" });
    expect(currentDownloadBtn).not.toBeDisabled();
    expect(currentDownloadBtn).toHaveTextContent("Download PDF");
  });

  it("token change during a pending download invalidates the download", async () => {
    URL.createObjectURL = vi.fn(() => "blob:test");
    URL.revokeObjectURL = vi.fn();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const downloadDeferred = deferred();
    downloadReportPdf.mockReturnValueOnce(downloadDeferred.promise);

    const { rerender } = render(<ReportWorkspace accessToken="token-1" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const downloadBtn = screen.getByRole("button", { name: "Download PDF" });
    fireEvent.click(downloadBtn);

    expect(downloadBtn).toBeDisabled();
    expect(downloadBtn).toHaveTextContent("Preparing PDF…");

    rerender(<ReportWorkspace accessToken="token-2" />);

    await act(async () => {
      downloadDeferred.resolve({
        blob: new Blob(["%PDF-1.4 demo"]),
        filename: "agentic-grc-report-token1.pdf",
      });
    });

    expect(clickSpy).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(screen.queryByText("Report downloaded.")).not.toBeInTheDocument();
  });

  it("stale download failure does not show an error alert", async () => {
    const downloadDeferred = deferred();
    downloadReportPdf.mockReturnValueOnce(downloadDeferred.promise);

    render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const downloadBtn = screen.getByRole("button", { name: "Download PDF" });
    fireEvent.click(downloadBtn);

    const select = screen.getByLabelText("Organization");
    fireEvent.change(select, { target: { value: "org-2" } });

    await act(async () => {
      downloadDeferred.reject({
        status: 404,
        message: "Assessment not found.",
      });
    });

    expect(
      screen.queryByText("No report is available for this organization yet.")
    ).not.toBeInTheDocument();
  });

  it("unmount during a pending download does not save file or trigger unmounted warnings", async () => {
    URL.createObjectURL = vi.fn(() => "blob:test");
    URL.revokeObjectURL = vi.fn();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const downloadDeferred = deferred();
    downloadReportPdf.mockReturnValueOnce(downloadDeferred.promise);

    const { unmount } = render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const downloadBtn = screen.getByRole("button", { name: "Download PDF" });
    fireEvent.click(downloadBtn);

    unmount();

    await act(async () => {
      downloadDeferred.resolve({
        blob: new Blob(["%PDF-1.4 demo"]),
        filename: "agentic-grc-report.pdf",
      });
    });

    expect(clickSpy).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  it("token change never requests the previous organization's preview with the new token", async () => {
    const { rerender } = render(<ReportWorkspace accessToken="token-1" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });
    expect(getReportPreview).toHaveBeenCalledWith("org-1", "assess-1", "token-1");

    const token2OrgsPending = deferred();
    listOrganizations.mockReturnValueOnce(token2OrgsPending.promise);

    // On the token change, the preview effect runs in the same render as the old selection (org-1).
    rerender(<ReportWorkspace accessToken="token-2" />);
    await act(async () => {});

    expect(getReportPreview).not.toHaveBeenCalledWith("org-1", "assess-1", "token-2");
    expect(getReportPreview).toHaveBeenCalledTimes(1);

    // The new session does not include org-1, so a call with org-1 and token-2 is never legitimate.
    await act(async () => {
      token2OrgsPending.resolve([mockOrganizations[1]]);
    });

    await waitFor(() => {
      expect(getReportPreview).toHaveBeenCalledWith("org-2", "assess-1", "token-2");
    });
    expect(getReportPreview).not.toHaveBeenCalledWith("org-1", "assess-1", "token-2");
    expect(getReportPreview).toHaveBeenCalledTimes(2);
  });

  it("shows 'Evidence pending' badge only on rows where evidence_pending is true", async () => {
    getReportPreview.mockResolvedValueOnce(mockReportViewWithEvidencePending);

    render(<ReportWorkspace accessToken="test-token" />);

    const table = await screen.findByRole("table", { name: "Reviewed results" });
    const row1 = within(table).getByText("PR.AA-01").closest("tr");
    const row2 = within(table).getByText("PR.AA-03").closest("tr");

    expect(within(row1).getByText("Implemented")).toBeInTheDocument();
    const badge = within(row1).getByText("Evidence pending");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("report-evidence-badge");

    expect(within(row2).getByText("Partially implemented")).toBeInTheDocument();
    expect(within(row2).queryByText("Evidence pending")).not.toBeInTheDocument();
  });

  it("renders the 'Final results with evidence pending' summary tile", async () => {
    const { unmount } = render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const defaultSummary = screen.getByText("Controls in scope").closest("dl");
    expect(
      within(defaultSummary).getByText("Final results with evidence pending").parentElement
    ).toHaveTextContent("0");

    unmount();

    getReportPreview.mockResolvedValueOnce(mockReportViewWithEvidencePending);
    render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const variantSummary = screen.getByText("Controls in scope").closest("dl");
    expect(
      within(variantSummary).getByText("Final results with evidence pending").parentElement
    ).toHaveTextContent("1");
  });

  it("renders the explanatory note only when final_with_evidence_pending > 0", async () => {
    const { unmount } = render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    expect(
      screen.queryByText(/Results marked “Evidence pending” were accepted by an Aligo consultant/)
    ).not.toBeInTheDocument();

    unmount();

    getReportPreview.mockResolvedValueOnce(mockReportViewWithEvidencePending);
    render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const note = screen.getByText(
      /Results marked “Evidence pending” were accepted by an Aligo consultant on the basis of the participant's statement; the supporting evidence has not been validated yet\./
    );
    expect(note).toBeInTheDocument();
    expect(note).toHaveClass("report-evidence-note");
  });

  it("tolerates missing final_with_evidence_pending in summary and renders 0", async () => {
    const { final_with_evidence_pending: _discarded, ...summaryWithoutField } =
      mockReportView.summary;
    const previewWithoutField = {
      ...mockReportView,
      summary: summaryWithoutField,
    };
    getReportPreview.mockResolvedValueOnce(previewWithoutField);

    render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const summary = screen.getByText("Controls in scope").closest("dl");
    expect(
      within(summary).getByText("Final results with evidence pending").parentElement
    ).toHaveTextContent("0");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("revokes the download object URL after click via timer, exactly once, and never for stale downloads", async () => {
    URL.createObjectURL = vi.fn(() => "blob:test-timer");
    URL.revokeObjectURL = vi.fn();
    let clicked = false;
    let revokedBeforeTimers = null;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      clicked = true;
      // A microtask runs after the rest of the synchronous code but before any setTimeout callback,
      // so this is true only if the URL was revoked synchronously right after the click.
      queueMicrotask(() => {
        revokedBeforeTimers = URL.revokeObjectURL.mock.calls.length > 0;
      });
    });

    const downloadDeferred = deferred();
    downloadReportPdf.mockReturnValueOnce(downloadDeferred.promise);

    render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const downloadBtn = screen.getByRole("button", { name: "Download PDF" });
    fireEvent.click(downloadBtn);

    downloadDeferred.resolve({
      blob: new Blob(["%PDF-1.4 demo"]),
      filename: "agentic-grc-report.pdf",
    });

    await waitFor(() => {
      expect(clicked).toBe(true);
      expect(revokedBeforeTimers).not.toBeNull();
    });
    expect(revokedBeforeTimers).toBe(false);

    await waitFor(() => {
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-timer");
    });
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);

    URL.revokeObjectURL.mockClear();
    URL.createObjectURL.mockClear();

    const staleDeferred = deferred();
    downloadReportPdf.mockReturnValueOnce(staleDeferred.promise);

    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));

    fireEvent.change(screen.getByLabelText("Organization"), {
      target: { value: "org-2" },
    });

    await act(async () => {
      staleDeferred.resolve({
        blob: new Blob(["%PDF-1.4 demo"]),
        filename: "stale.pdf",
      });
    });

    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  });

  it("requests assessments for the selected organization, then the preview for the first assessment", async () => {
    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    expect(listOrganizations).toHaveBeenCalledWith("test-token");
    expect(listAssessments).toHaveBeenCalledWith("org-1", "test-token");
    expect(getReportPreview).toHaveBeenCalledWith("org-1", "assess-1", "test-token");
  });

  it("with 2 assessments: the picker shows both labels (title · status · date); choosing the second requests its preview", async () => {
    listAssessments.mockResolvedValueOnce([
      {
        id: "assess-1",
        title: "Identity and access",
        status: "in_progress",
        started_at: "2026-10-13T09:00:00Z",
      },
      {
        id: "assess-2",
        title: "Network security",
        status: "awaiting_review",
        started_at: "2026-09-01T12:00:00Z",
      },
    ]);

    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const select = screen.getByLabelText("Assessment");
    expect(select).toBeInTheDocument();

    const options = within(select).getAllByRole("option");
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent("Identity and access · In progress · 2026-10-13");
    expect(options[1]).toHaveTextContent("Network security · Awaiting review · 2026-09-01");

    fireEvent.change(select, { target: { value: "assess-2" } });

    await waitFor(() => {
      expect(getReportPreview).toHaveBeenCalledWith("org-1", "assess-2", "test-token");
    });
  });

  it("with 0 assessments: shows 'No assessments yet for this organization.' and getReportPreview is not called", async () => {
    listAssessments.mockResolvedValueOnce([]);

    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByText("No assessments yet for this organization.");

    expect(getReportPreview).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Assessment")).not.toBeInTheDocument();
  });

  it("exactly 1 assessment: shows 'Assessment: Identity and access' and no select", async () => {
    listAssessments.mockResolvedValueOnce([
      {
        id: "assess-1",
        title: "Identity and access",
        status: "in_progress",
        started_at: "2026-10-13T09:00:00Z",
      },
    ]);

    render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    expect(screen.getByText("Assessment: Identity and access")).toBeInTheDocument();
    expect(screen.queryByLabelText("Assessment")).not.toBeInTheDocument();
  });

  it("assessment list error 401 -> session-expired alert; 'Try again' calls listAssessments again", async () => {
    listAssessments.mockRejectedValueOnce({
      status: 401,
      message: "Could not validate credentials.",
    });

    render(<ReportWorkspace accessToken="test-token" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Your session has expired. Sign in again to continue.");
    expect(getReportPreview).not.toHaveBeenCalled();

    listAssessments.mockResolvedValueOnce(mockAssessments);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });
    expect(listAssessments).toHaveBeenCalledTimes(2);
  });

  it("stale assessments: the list for org A resolves after switching to org B -> only B's assessments are shown and only B's preview is requested", async () => {
    const assessmentsA = deferred();
    const assessmentsB = deferred();

    listAssessments.mockImplementation((orgId) => {
      if (orgId === "org-1") return assessmentsA.promise;
      if (orgId === "org-2") return assessmentsB.promise;
      return Promise.reject(new Error("Unknown org"));
    });

    render(<ReportWorkspace accessToken="test-token" />);

    const orgSelect = await screen.findByLabelText("Organization");
    fireEvent.change(orgSelect, { target: { value: "org-2" } });

    await act(async () => {
      assessmentsB.resolve([
        {
          id: "assess-b",
          title: "Org B Assessment",
          status: "completed",
        },
      ]);
    });

    await screen.findByText("Assessment: Org B Assessment");

    await act(async () => {
      assessmentsA.resolve([
        {
          id: "assess-a",
          title: "Org A Assessment",
          status: "draft",
        },
      ]);
    });

    expect(screen.getByText("Assessment: Org B Assessment")).toBeInTheDocument();
    expect(screen.queryByText("Assessment: Org A Assessment")).not.toBeInTheDocument();
    expect(getReportPreview).toHaveBeenCalledWith("org-2", "assess-b", "test-token");
    expect(getReportPreview).not.toHaveBeenCalledWith("org-1", expect.anything(), expect.anything());
    expect(getReportPreview).not.toHaveBeenCalledWith(expect.anything(), "assess-a", expect.anything());
  });

  it("organization change never requests the new organization's preview with the previous organization's assessment", async () => {
    listAssessments.mockImplementation((orgId) =>
      Promise.resolve(
        orgId === "org-1"
          ? [{ id: "assess-a", title: "Org A Assessment", status: "in_progress" }]
          : [{ id: "assess-b", title: "Org B Assessment", status: "in_progress" }]
      )
    );

    render(<ReportWorkspace accessToken="test-token" />);

    // Organization A is fully loaded (assessment selected, preview shown) before the switch.
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });
    expect(getReportPreview).toHaveBeenCalledWith("org-1", "assess-a", "test-token");

    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "org-2" } });

    await waitFor(() => {
      expect(getReportPreview).toHaveBeenCalledWith("org-2", "assess-b", "test-token");
    });
    expect(getReportPreview).not.toHaveBeenCalledWith("org-2", "assess-a", "test-token");
    expect(getReportPreview).toHaveBeenCalledTimes(2);
  });

  it("stale preview on assessment change: preview for assessment 1 resolves after selecting assessment 2 -> only assessment 2's data is shown", async () => {
    listAssessments.mockResolvedValueOnce([
      {
        id: "assess-1",
        title: "Assessment 1",
        status: "in_progress",
      },
      {
        id: "assess-2",
        title: "Assessment 2",
        status: "in_progress",
      },
    ]);

    const preview1 = deferred();
    const preview2 = deferred();

    getReportPreview.mockImplementation((_orgId, assessId) => {
      if (assessId === "assess-1") return preview1.promise;
      if (assessId === "assess-2") return preview2.promise;
      return Promise.reject(new Error("Unknown assessment"));
    });

    render(<ReportWorkspace accessToken="test-token" />);

    const assessSelect = await screen.findByLabelText("Assessment");
    fireEvent.change(assessSelect, { target: { value: "assess-2" } });

    await act(async () => {
      preview2.resolve({
        ...mockReportView,
        assessment: {
          ...mockReportView.assessment,
          id: "assess-2",
          title: "Assessment 2 Title",
        },
      });
    });

    await screen.findByRole("heading", { name: "Assessment 2 Title" });

    await act(async () => {
      preview1.resolve({
        ...mockReportView,
        assessment: {
          ...mockReportView.assessment,
          id: "assess-1",
          title: "Assessment 1 Title",
        },
      });
    });

    expect(screen.getByRole("heading", { name: "Assessment 2 Title" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Assessment 1 Title" })).not.toBeInTheDocument();
  });

  it("stale download on assessment change: download pending for assessment 1 -> select assessment 2 -> resolve -> no createObjectURL, no click, no 'Report downloaded.'; button enabled", async () => {
    listAssessments.mockResolvedValue([
      {
        id: "assess-1",
        title: "Assessment 1",
        status: "in_progress",
      },
      {
        id: "assess-2",
        title: "Assessment 2",
        status: "in_progress",
      },
    ]);

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

    const select = screen.getByLabelText("Assessment");
    fireEvent.change(select, { target: { value: "assess-2" } });

    await act(async () => {
      downloadDeferred.resolve({
        blob: new Blob(["%PDF-1.4 demo"]),
        filename: "agentic-grc-report-assess1.pdf",
      });
    });

    expect(clickSpy).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(screen.queryByText("Report downloaded.")).not.toBeInTheDocument();

    const currentDownloadBtn = await screen.findByRole("button", { name: "Download PDF" });
    expect(currentDownloadBtn).not.toBeDisabled();
    expect(currentDownloadBtn).toHaveTextContent("Download PDF");
  });

  it("download uses the selected assessment id", async () => {
    listAssessments.mockResolvedValueOnce([
      {
        id: "assess-1",
        title: "Assessment 1",
        status: "in_progress",
      },
      {
        id: "assess-2",
        title: "Assessment 2",
        status: "in_progress",
      },
    ]);

    downloadReportPdf.mockResolvedValueOnce({
      blob: new Blob(["%PDF-1.4 demo"]),
      filename: "agentic-grc-report.pdf",
    });

    render(<ReportWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const select = screen.getByLabelText("Assessment");
    fireEvent.change(select, { target: { value: "assess-2" } });

    await screen.findByRole("heading", { name: "Identity and access — demo assessment" });

    const downloadBtn = screen.getByRole("button", { name: "Download PDF" });
    fireEvent.click(downloadBtn);

    expect(downloadReportPdf).toHaveBeenCalledWith("org-1", "assess-2", "test-token");
  });

  it("demo option: with VITE_SHOW_DEMO_REPORT='true' and 0 real assessments -> demo assessment shown and preview requested; unset -> empty message and no demo", async () => {
    listAssessments.mockResolvedValue([]);

    // 1. With variable unset
    const { unmount } = render(<ReportWorkspace accessToken="test-token" />);

    await screen.findByText("No assessments yet for this organization.");
    expect(getReportPreview).not.toHaveBeenCalled();
    expect(screen.queryByText(/Demo assessment/)).not.toBeInTheDocument();

    unmount();
    getReportPreview.mockClear();
    listAssessments.mockResolvedValue([]);

    // 2. With VITE_SHOW_DEMO_REPORT = "true"
    vi.stubEnv("VITE_SHOW_DEMO_REPORT", "true");
    try {
      render(<ReportWorkspace accessToken="test-token" />);

      await screen.findByText("Assessment: Demo assessment (sample data)");
      expect(getReportPreview).toHaveBeenCalledWith("org-1", DEMO_ASSESSMENT_ID, "test-token");
    } finally {
      vi.unstubAllEnvs();
    }
  });
});

