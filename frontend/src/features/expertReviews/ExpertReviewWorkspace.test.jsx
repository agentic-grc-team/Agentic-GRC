import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import ExpertReviewWorkspace from "./ExpertReviewWorkspace.jsx";
import {
  listPendingReviews,
  submitReviewDecision,
} from "./api.js";


vi.mock("./api.js", () => ({
  listPendingReviews: vi.fn(),
  submitReviewDecision: vi.fn(),
}));


const pendingReview = {
  result_id: "result-demo-001",
  assessment_id: "assessment-demo-001",
  control_code: "PR.AA-03",
  control_title: "Users, services, and hardware are authenticated",
  control_status: "partially_implemented",
  maturity_current: 2,
  confidence: 0.78,
  explanation: "MFA is enabled for some administrator accounts.",
  evidence_summary: "The policy and configuration evidence disagree.",
  requires_human_review: true,
};


describe("ExpertReviewWorkspace", () => {
  beforeEach(() => {
    vi.resetAllMocks();

    listPendingReviews.mockResolvedValue([pendingReview]);

    submitReviewDecision.mockResolvedValue({
      result_id: "result-demo-001",
      outcome: "accepted",
      comment: "",
      message: "Review decision received successfully.",
    });
  });

  it("loads and displays a pending AI result", async () => {
    render(
      <ExpertReviewWorkspace accessToken="test-token" />,
    );

    expect(
      await screen.findByRole("heading", {
        name: "PR.AA-03",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "Users, services, and hardware are authenticated",
      ),
    ).toBeInTheDocument();

    expect(screen.getByText("78%")).toBeInTheDocument();

    expect(listPendingReviews).toHaveBeenCalledWith(
      "test-token",
    );
  });

  it("requires a comment when rejecting a result", async () => {
    render(
      <ExpertReviewWorkspace accessToken="test-token" />,
    );

    await screen.findByRole("heading", {
      name: "PR.AA-03",
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Reject",
      }),
    );

    expect(
      screen.getByRole("alert"),
    ).toHaveTextContent(
      "A review comment is required when modifying or rejecting a result.",
    );

    expect(
      submitReviewDecision,
    ).not.toHaveBeenCalled();
  });

  it("submits an accepted decision and clears the queue", async () => {
    render(
      <ExpertReviewWorkspace accessToken="test-token" />,
    );

    await screen.findByRole("heading", {
      name: "PR.AA-03",
    });

    fireEvent.change(
      screen.getByLabelText("Review comment"),
      {
        target: {
          value: "  Evidence is sufficient.  ",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Accept",
      }),
    );

    await waitFor(() => {
      expect(
        submitReviewDecision,
      ).toHaveBeenCalledWith(
        "result-demo-001",
        "accepted",
        "Evidence is sufficient.",
        "test-token",
      );
    });

    expect(
      await screen.findByRole("heading", {
        name: "Review queue complete",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("status"),
    ).toHaveTextContent(
      "The result was successfully accepted.",
    );
  });
  it("preserves the result and comment when submission fails", async () => {
    submitReviewDecision.mockRejectedValueOnce(
      new Error("Unable to submit review."),
    );

    render(<ExpertReviewWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "PR.AA-03" });

    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: { value: "Evidence needs another check." },
    });

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to submit review.",
    );

    expect(
      screen.getByRole("heading", { name: "PR.AA-03" }),
    ).toBeInTheDocument();

    expect(screen.getByLabelText("Review comment")).toHaveValue(
      "Evidence needs another check.",
    );

    expect(
      screen.getByRole("button", { name: "Accept" }),
    ).toBeEnabled();
  });


  it("disables the form while submitting a decision", async () => {
    let resolveSubmission;

    submitReviewDecision.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSubmission = resolve;
        }),
    );

    render(<ExpertReviewWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "PR.AA-03" });

    const acceptButton = screen.getByRole("button", { name: "Accept" });

    fireEvent.click(acceptButton);

    expect(acceptButton).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Mark as modified" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Reject" }),
    ).toBeDisabled();
    expect(screen.getByLabelText("Review comment")).toBeDisabled();

    fireEvent.click(acceptButton);

    expect(submitReviewDecision).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveSubmission({
        result_id: pendingReview.result_id,
        outcome: "accepted",
        comment: "",
        message: "Review decision received successfully.",
      });
    });

    expect(
      screen.getByRole("heading", { name: "Review queue complete" }),
    ).toBeInTheDocument();
  });


  it("ignores an old loading response after the token changes", async () => {
    let resolveOldRequest;

    listPendingReviews.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOldRequest = resolve;
        }),
    );

    const newReview = {
      ...pendingReview,
      result_id: "result-new-session",
      control_code: "PR.AA-05",
    };

    listPendingReviews.mockResolvedValueOnce([newReview]);

    const { rerender } = render(
      <ExpertReviewWorkspace accessToken="old-token" />,
    );

    rerender(<ExpertReviewWorkspace accessToken="new-token" />);

    expect(
      await screen.findByRole("heading", { name: "PR.AA-05" }),
    ).toBeInTheDocument();

    expect(listPendingReviews).toHaveBeenNthCalledWith(1, "old-token");
    expect(listPendingReviews).toHaveBeenNthCalledWith(2, "new-token");

    await act(async () => {
      resolveOldRequest([pendingReview]);
    });

    expect(
      screen.getByRole("heading", { name: "PR.AA-05" }),
    ).toBeInTheDocument();

    expect(
      screen.queryByRole("heading", { name: "PR.AA-03" }),
    ).not.toBeInTheDocument();
  });
});