import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getPassageMatches } from "../assessments/api.js";
import ProposedPassages from "./ProposedPassages.jsx";

vi.mock("../assessments/api.js", () => ({ getPassageMatches: vi.fn() }));

const response = {
  organization_id: "org-1",
  assessment_id: "assess-1",
  files_checked: 2,
  matcher_version: "lexical-0.1",
  controls_without_terms: ["DE.CM-01"],
  matches: [{
    control_code: "PR.AA-03",
    evidence_file_id: "file-1",
    file_name: "mfa-policy.pdf",
    reference: "document_span:file-1#page=2",
    locator: { page: 2, section: "Access Control", char_start: 30, char_end: 90 },
    excerpt: "All administrators must use multi-factor authentication.",
    matched_terms: ["mfa", "administrator"],
    confidence: 0.75,
    linked: false,
  }],
};

function show(props = {}) {
  return render(
    <ProposedPassages
      organizationId="org-1"
      assessmentId="assess-1"
      controlCode="PR.AA-03"
      accessToken="token-a"
      sessionId="user-1"
      {...props}
    />,
  );
}

describe("ProposedPassages", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows unverified passages for the reviewed control only", async () => {
    getPassageMatches.mockResolvedValue({
      ...response,
      matches: [
        ...response.matches,
        { ...response.matches[0], control_code: "PR.AA-01", excerpt: "Different control." },
      ],
    });
    show();

    expect(getPassageMatches).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Find relevant passages" }));

    const list = await screen.findByRole("list", { name: "Passages for PR.AA-03" });
    expect(getPassageMatches).toHaveBeenCalledWith("org-1", "assess-1", "token-a");
    expect(within(list).getByText("mfa-policy.pdf")).toBeInTheDocument();
    expect(within(list).getByText("All administrators must use multi-factor authentication.")).toBeInTheDocument();
    expect(within(list).getByText(/Page 2 · Section Access Control/)).toBeInTheDocument();
    expect(screen.queryByText("Different control.")).not.toBeInTheDocument();
    expect(screen.getByText(/proposed matches are unverified/i)).toBeInTheDocument();
  });

  it("shows an empty state when no passage matches the selected control", async () => {
    getPassageMatches.mockResolvedValue({ ...response, matches: [] });
    show();
    fireEvent.click(screen.getByRole("button", { name: "Find relevant passages" }));
    expect(await screen.findByText("No matching passages found in 2 documents checked."))
      .toBeInTheDocument();
  });

  it("rejects matches from another assessment", async () => {
    getPassageMatches.mockResolvedValue({ ...response, assessment_id: "assess-other" });
    show();
    fireEvent.click(screen.getByRole("button", { name: "Find relevant passages" }));
    expect(await screen.findByRole("alert"))
      .toHaveTextContent("Passage matches do not belong to this assessment.");
    expect(screen.queryByText("mfa-policy.pdf")).not.toBeInTheDocument();
  });
});