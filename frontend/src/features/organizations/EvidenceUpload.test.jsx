import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
