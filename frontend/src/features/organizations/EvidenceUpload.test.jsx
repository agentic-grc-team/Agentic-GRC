import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EvidenceUpload from "./EvidenceUpload.jsx";
import { uploadEvidence } from "./api.js";

vi.mock("./api.js", () => ({ uploadEvidence: vi.fn() }));

beforeEach(() => {
  vi.resetAllMocks();
  uploadEvidence.mockResolvedValue({ extracted_content_preview: "Evidence" });
});

describe("EvidenceUpload", () => {
  it("rejects unsupported and oversized files before sending requests", async () => {
    const { container } = render(<EvidenceUpload organizationId="alpha" accessToken="token" />);
    const input = container.querySelector("input[type=file]");
    fireEvent.change(input, { target: { files: [new File(["invalid"], "file.exe")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Format not allowed");
    const large = new File(["synthetic"], "large.txt");
    Object.defineProperty(large, "size", { value: 10 * 1024 * 1024 + 1 });
    fireEvent.change(input, { target: { files: [large] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("10MB");
    expect(uploadEvidence).not.toHaveBeenCalled();
  });

  it("keeps keyboard activation disabled until an organization is selected", () => {
    const { container } = render(<EvidenceUpload organizationId="" accessToken="token" />);
    const inputClick = vi.spyOn(container.querySelector("input[type=file]"), "click");
    fireEvent.keyDown(screen.getByRole("button"), { key: "Enter" });
    expect(inputClick).not.toHaveBeenCalled();
    expect(uploadEvidence).not.toHaveBeenCalled();
  });

  it("reports membership errors and allows retrying", async () => {
    uploadEvidence.mockRejectedValueOnce({ status: 403, message: "Forbidden" });
    const { container } = render(<EvidenceUpload organizationId="alpha" accessToken="token" />);
    const upload = () => fireEvent.change(container.querySelector("input[type=file]"), { target: { files: [new File(["evidence"], "policy.txt")] } });
    upload();
    expect(await screen.findByRole("alert")).toHaveTextContent("active membership");
    upload();
    await screen.findByText("Evidence");
    expect(uploadEvidence).toHaveBeenCalledTimes(2);
  });

  it("renders extracted HTML as text", async () => {
    const html = '<img src="x" onerror="alert(1)">';
    uploadEvidence.mockResolvedValueOnce({ extracted_content_preview: html });
    const { container } = render(<EvidenceUpload organizationId="alpha" accessToken="token" />);
    fireEvent.change(container.querySelector("input[type=file]"), { target: { files: [new File(["evidence"], "policy.txt")] } });
    await screen.findByText(html);
    expect(container.querySelector(".evidence-preview img")).toBeNull();
  });
});

describe("EvidenceUpload for an assessment", () => {
  it("uploads to the assessment and reports the stored file", async () => {
    const stored = { id: "file-1", extracted_content_preview: "Evidence" };
    uploadEvidence.mockResolvedValueOnce(stored);
    const onUploaded = vi.fn();
    const { container } = render(
      <EvidenceUpload organizationId="alpha" assessmentId="assess-1" accessToken="token" onUploaded={onUploaded} />,
    );
    fireEvent.change(container.querySelector("input[type=file]"), { target: { files: [new File(["evidence"], "policy.txt")] } });
    await screen.findByText("Evidence");
    expect(uploadEvidence).toHaveBeenCalledWith("alpha", expect.any(File), "token", expect.any(AbortSignal), "assess-1");
    expect(onUploaded).toHaveBeenCalledWith(stored);
  });

  it("does not report a failed upload", async () => {
    uploadEvidence.mockRejectedValueOnce({ status: 422, message: "Document contains no readable text." });
    const onUploaded = vi.fn();
    const { container } = render(
      <EvidenceUpload organizationId="alpha" assessmentId="assess-1" accessToken="token" onUploaded={onUploaded} />,
    );
    fireEvent.change(container.querySelector("input[type=file]"), { target: { files: [new File(["evidence"], "policy.txt")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("no readable text");
    expect(onUploaded).not.toHaveBeenCalled();
  });
});
describe("EvidenceUpload session changes", () => {
  const drop = () => fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [new File(["evidence"], "policy.txt")] } });

  it("ignores a pending upload and clears the preview when the session changes for the same organization", async () => {
    let resolveUpload;
    uploadEvidence.mockImplementationOnce(() => new Promise((resolve) => { resolveUpload = resolve; }));
    const { rerender } = render(<EvidenceUpload organizationId="alpha" accessToken="token-a" sessionId="user-a" />);
    drop();
    await screen.findByText("Uploading policy.txt...");
    const signal = uploadEvidence.mock.calls[0][3];

    rerender(<EvidenceUpload organizationId="alpha" accessToken="token-b" sessionId="user-b" />);
    expect(signal.aborted).toBe(true);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    await act(async () => { resolveUpload({ extracted_content_preview: "Previous session preview" }); });
    expect(screen.queryByText("Previous session preview")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("ignores a late error from the previous session", async () => {
    let rejectUpload;
    uploadEvidence.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectUpload = reject; }));
    const { rerender } = render(<EvidenceUpload organizationId="alpha" accessToken="token-a" sessionId="user-a" />);
    drop();
    await screen.findByText("Uploading policy.txt...");

    rerender(<EvidenceUpload organizationId="alpha" accessToken="token-b" sessionId="user-b" />);
    await act(async () => { rejectUpload({ status: 500, message: "Internal server error." }); });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("clears a completed preview when the session changes", async () => {
    const { rerender } = render(<EvidenceUpload organizationId="alpha" accessToken="token-a" sessionId="user-a" />);
    drop();
    await screen.findByText("Evidence");

    rerender(<EvidenceUpload organizationId="alpha" accessToken="token-b" sessionId="user-b" />);
    expect(screen.queryByText("Evidence")).not.toBeInTheDocument();
  });

  it("keeps the preview and a pending upload when the same session only refreshes its token", async () => {
    let resolveUpload;
    uploadEvidence.mockImplementationOnce(() => new Promise((resolve) => { resolveUpload = resolve; }));
    const { rerender } = render(<EvidenceUpload organizationId="alpha" accessToken="token-1" sessionId="user-a" />);
    drop();
    await screen.findByText("Uploading policy.txt...");

    rerender(<EvidenceUpload organizationId="alpha" accessToken="token-2" sessionId="user-a" />);
    expect(uploadEvidence.mock.calls[0][3].aborted).toBe(false);
    await act(async () => { resolveUpload({ extracted_content_preview: "Finished upload" }); });
    expect(screen.getByText("Finished upload")).toBeInTheDocument();

    rerender(<EvidenceUpload organizationId="alpha" accessToken="token-3" sessionId="user-a" />);
    expect(screen.getByText("Finished upload")).toBeInTheDocument();
  });

  it("uploads with the most recent token after a refresh", async () => {
    const { rerender } = render(<EvidenceUpload organizationId="alpha" accessToken="token-1" sessionId="user-a" />);
    rerender(<EvidenceUpload organizationId="alpha" accessToken="token-2" sessionId="user-a" />);
    drop();
    await screen.findByText("Evidence");
    expect(uploadEvidence).toHaveBeenCalledWith("alpha", expect.any(File), "token-2", expect.any(AbortSignal), "");
  });

  it("aborts the request and ignores the response after unmount", async () => {
    let resolveUpload;
    uploadEvidence.mockImplementationOnce(() => new Promise((resolve) => { resolveUpload = resolve; }));
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { unmount } = render(<EvidenceUpload organizationId="alpha" accessToken="token" sessionId="user-a" />);
    drop();
    await screen.findByText("Uploading policy.txt...");
    const signal = uploadEvidence.mock.calls[0][3];

    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => { resolveUpload({ extracted_content_preview: "Late" }); });
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});