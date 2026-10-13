import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EvidencePage from "./EvidencePage.jsx";
import { listOrganizations, uploadEvidence } from "./api.js";

vi.mock("./api.js", () => ({ listOrganizations: vi.fn(), uploadEvidence: vi.fn() }));

const organizations = [{ id: "alpha", name: "Alpha" }, { id: "beta", name: "Beta" }];
const result = { organization_id: "alpha", original_filename: "alpha.txt", extracted_content_preview: "Alpha document" };
const file = () => new File(["Alpha document"], "alpha.txt", { type: "text/plain" });
const dropzone = () => screen.getByRole("button", { name: /Drag and drop a file here/ });
const drop = () => fireEvent.drop(dropzone(), { dataTransfer: { files: [file()] } });

beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState({}, "", "/evidence?organization_id=alpha");
  listOrganizations.mockResolvedValue(organizations);
  uploadEvidence.mockResolvedValue(result);
});

async function page() {
  const rendered = render(<EvidencePage accessToken="token" onNavigate={vi.fn()} />);
  await screen.findByRole("combobox");
  return rendered;
}

describe("EvidencePage organization context", () => {
  it("requests active memberships and preserves an eligible organization from the URL", async () => {
    window.history.replaceState({}, "", "/evidence?organization_id=beta");
    await page();
    expect(listOrganizations).toHaveBeenCalledWith("token", { activeMembershipsOnly: true });
    expect(screen.getByRole("combobox")).toHaveValue("beta");
    expect(screen.getByText("Beta", { selector: "strong" })).toBeInTheDocument();
    drop();
    await waitFor(() => expect(uploadEvidence).toHaveBeenCalledWith("beta", expect.any(File), "token", expect.any(AbortSignal)));
  });

  it("requires an explicit selection without URL context", async () => {
    window.history.replaceState({}, "", "/evidence");
    await page();
    expect(screen.getByRole("combobox")).toHaveValue("");
    expect(dropzone()).toHaveAttribute("aria-disabled", "true");
    drop();
    expect(uploadEvidence).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "beta" } });
    expect(dropzone()).toHaveAttribute("aria-disabled", "false");
    expect(window.location.search).toContain("organization_id=beta");
  });

  it("rejects unavailable organization context instead of falling back to another client", async () => {
    window.history.replaceState({}, "", "/evidence?organization_id=unavailable");
    await page();
    expect(screen.getByRole("combobox")).toHaveValue("");
    expect(dropzone()).toHaveAttribute("aria-disabled", "true");
    drop();
    expect(uploadEvidence).not.toHaveBeenCalled();
  });

  it("clears a completed preview when switching organizations", async () => {
    await page();
    drop();
    await screen.findByText("Alpha document");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "beta" } });
    expect(screen.queryByText("Alpha document")).not.toBeInTheDocument();
    expect(screen.queryByText("File uploaded and parsed successfully.")).not.toBeInTheDocument();
  });

  it("ignores a previous organization's late response while allowing a new upload", async () => {
    let resolveAlpha;
    uploadEvidence.mockImplementationOnce(() => new Promise((resolve) => { resolveAlpha = resolve; }));
    await page();
    drop();
    await screen.findByText("Uploading alpha.txt...");
    const alphaSignal = uploadEvidence.mock.calls[0][3];
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "beta" } });
    expect(alphaSignal.aborted).toBe(true);
    uploadEvidence.mockResolvedValueOnce({ ...result, organization_id: "beta", extracted_content_preview: "Beta document" });
    drop();
    await screen.findByText("Beta document");
    await act(async () => { resolveAlpha(result); });
    expect(screen.queryByText("Alpha document")).not.toBeInTheDocument();
    expect(screen.getByText("Beta document")).toBeInTheDocument();
  });

  it("recovers from an expired token without retaining the error", async () => {
    listOrganizations.mockRejectedValueOnce({ status: 401 });
    const rendered = render(<EvidencePage accessToken="expired" onNavigate={vi.fn()} />);
    await screen.findByRole("alert");
    rendered.rerender(<EvidencePage accessToken="refreshed" onNavigate={vi.fn()} />);
    await screen.findByRole("combobox");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("retries a failed organization load", async () => {
    listOrganizations.mockRejectedValueOnce(new Error("Network unavailable"));
    await render(<EvidencePage accessToken="token" onNavigate={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry loading organizations" }));
    await screen.findByRole("combobox");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(listOrganizations).toHaveBeenCalledTimes(2);
  });
});
