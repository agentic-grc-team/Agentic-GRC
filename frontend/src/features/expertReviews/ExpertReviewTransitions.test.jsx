import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ExpertReviewWorkspace from "./ExpertReviewWorkspace.jsx";
import { listPendingReviews, submitReviewDecision } from "./api.js";

vi.mock("./api.js", () => ({
  listPendingReviews: vi.fn(),
  submitReviewDecision: vi.fn(),
}));
vi.mock("./ReviewEvidence.jsx", () => ({ default: () => null }));
vi.mock("./ReviewTrace.jsx", () => ({ default: () => null }));

const firstResult = {
  result_id: "result-1",
  organization_id: "org-1",
  assessment_id: "assessment-1",
  assessment_title: "Beta assessment",
  control_code: "PR.AA-03",
  control_title: "Users are authenticated",
  control_status: "partially_implemented",
  explanation: "MFA is enabled for some accounts.",
};

describe("Expert Review transitions", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    submitReviewDecision.mockResolvedValue({ outcome: "accepted" });
  });

  afterEach(() => vi.useRealTimers());

  it("shows the next control and prevents a rapid second decision", async () => {
    listPendingReviews.mockResolvedValue([
      firstResult,
      { ...firstResult, result_id: "result-2", control_code: "PR.AA-04", control_title: "Identity assertions are protected" },
    ]);
    const scrollIntoView = vi.fn();
    const previousScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;

    try {
      render(<ExpertReviewWorkspace accessToken="test-token" />);
      await screen.findByRole("heading", { name: "PR.AA-03" });
      vi.useFakeTimers();

      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Accept" }));
      });

      expect(screen.getByRole("heading", { name: "PR.AA-04" })).toBeInTheDocument();
      expect(screen.getByText("Beta assessment", { selector: ".review-context strong" })).toBeInTheDocument();
      expect(screen.getByText("PR.AA-04 · Identity assertions are protected")).toBeInTheDocument();
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
      expect(screen.getByRole("status")).toHaveTextContent("successfully accepted");
      expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();
      fireEvent.click(screen.getByRole("button", { name: "Accept" }));
      expect(submitReviewDecision).toHaveBeenCalledTimes(1);

      act(() => vi.advanceTimersByTime(1000));
      expect(screen.getByRole("button", { name: "Accept" })).toBeEnabled();
      expect(screen.getByRole("status")).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(2000));
      expect(screen.getByRole("status")).toHaveClass("is-exiting");
      act(() => vi.advanceTimersByTime(250));
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    } finally {
      Element.prototype.scrollIntoView = previousScrollIntoView;
    }
  });

  it("stays on the completed assessment until the reviewer chooses another", async () => {
    listPendingReviews.mockResolvedValue([
      firstResult,
      { ...firstResult, result_id: "result-other", assessment_id: "assessment-other", assessment_title: "Other assessment", control_code: "PR.AA-05" },
    ]);
    render(<ExpertReviewWorkspace accessToken="test-token" />);
    await screen.findByRole("heading", { name: "PR.AA-03" });

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(await screen.findByRole("heading", { name: "Assessment review complete" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Beta assessment" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "PR.AA-05" })).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole("button", { name: "Review next assessment" })).toBeEnabled(), {
      timeout: 1500,
    });
    fireEvent.click(screen.getByRole("button", { name: "Review next assessment" }));
    expect(screen.getByRole("heading", { name: "PR.AA-05" })).toBeInTheDocument();
  });
});
