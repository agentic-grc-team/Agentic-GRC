import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getPassageMatches } from "./api.js";
import AssessmentPassages from "./AssessmentPassages.jsx";

vi.mock("./api.js", () => ({ getPassageMatches: vi.fn() }));

const scope = {
  functions: [{
    categories: [{
      controls: [
        { code: "PR.AA-03", title: "Users are authenticated" },
        { code: "DE.CM-01", title: "Networks are monitored" },
      ],
    }],
  }],
};

const response = {
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
    <AssessmentPassages
      scope={scope}
      organizationId="org-1"
      assessmentId="assess-1"
      accessToken="token-a"
      {...props}
    />,
  );
}

describe("AssessmentPassages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads only when asked and shows the passage, location and source", async () => {
    getPassageMatches.mockResolvedValue(response);
    show();

    expect(getPassageMatches).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Find relevant passages" }));

    const list = await screen.findByRole("list", { name: "Passages for PR.AA-03" });
    expect(getPassageMatches).toHaveBeenCalledWith("org-1", "assess-1", "token-a");
    expect(screen.getByText("1 matching passage from 1 document.")).toBeInTheDocument();
    expect(within(list).getByText("mfa-policy.pdf")).toBeInTheDocument();
    expect(within(list).getByText("All administrators must use multi-factor authentication.")).toBeInTheDocument();
    expect(within(list).getByText(/Page 2 · Section Access Control · Characters 30–90/)).toBeInTheDocument();
    expect(within(list).getByText(/Source: document_span:file-1#page=2/)).toBeInTheDocument();
    expect(within(list).getByText(/File not linked to this control/)).toBeInTheDocument();
    expect(screen.getByText(/not verified evidence or confirmed answers/)).toBeInTheDocument();
  });

  it("distinguishes a control without matcher terms from one with no matches", async () => {
    getPassageMatches.mockResolvedValue(response);
    show();
    fireEvent.click(screen.getByRole("button", { name: "Find relevant passages" }));
    await screen.findByText("mfa-policy.pdf");

    fireEvent.change(screen.getByRole("combobox", { name: "Control" }), {
      target: { value: "DE.CM-01" },
    });

    expect(screen.getByText(/Matching terms are not available for this control yet/)).toBeInTheDocument();
    expect(screen.queryByText("mfa-policy.pdf")).not.toBeInTheDocument();
    expect(getPassageMatches).toHaveBeenCalledTimes(1);
  });

  it("counts several passages from the same document once", async () => {
    getPassageMatches.mockResolvedValue({
      ...response,
      matches: [
        response.matches[0],
        { ...response.matches[0], locator: { ...response.matches[0].locator, char_start: 100 } },
      ],
    });
    show();

    fireEvent.click(screen.getByRole("button", { name: "Find relevant passages" }));

    expect(await screen.findByText("2 matching passages from 1 document.")).toBeInTheDocument();
  });

  it("shows an error and allows a retry", async () => {
    getPassageMatches
      .mockRejectedValueOnce(new Error("Service unavailable"))
      .mockResolvedValueOnce({ ...response, matches: [] });
    show();

    fireEvent.click(screen.getByRole("button", { name: "Find relevant passages" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");

    fireEvent.click(screen.getByRole("button", { name: "Find relevant passages" }));
    expect(await screen.findByText(/No matching passages found in 2 documents checked/))
      .toBeInTheDocument();
  });
});