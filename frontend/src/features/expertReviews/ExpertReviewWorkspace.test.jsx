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
      screen.getByRole("button", { name: "Edit result" }),
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
  it("ignores an old submission response after the token changes", async () => {
    let resolveOldSubmission;

    submitReviewDecision.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOldSubmission = resolve;
        }),
    );

    const { rerender } = render(
      <ExpertReviewWorkspace accessToken="old-token" />,
    );

    await screen.findByRole("heading", { name: "PR.AA-03" });

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    expect(submitReviewDecision).toHaveBeenCalledWith(
      pendingReview.result_id,
      "accepted",
      "",
      "old-token",
    );

    listPendingReviews.mockResolvedValueOnce([
      {
        ...pendingReview,
        result_id: "result-new-session",
        control_code: "PR.AA-05",
      },
    ]);

    rerender(<ExpertReviewWorkspace accessToken="new-token" />);

    await screen.findByRole("heading", { name: "PR.AA-05" });

    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: { value: "Comment for the new session." },
    });

    await act(async () => {
      resolveOldSubmission({
        result_id: pendingReview.result_id,
        outcome: "accepted",
        comment: "",
        message: "Review decision received successfully.",
      });
    });

    expect(
      screen.getByRole("heading", { name: "PR.AA-05" }),
    ).toBeInTheDocument();

    expect(screen.getByLabelText("Review comment")).toHaveValue(
      "Comment for the new session.",
    );

    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: "Accept" }),
    ).toBeEnabled();
  });
  it("opens the editor with the current result values", async () => {
    render(<ExpertReviewWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "PR.AA-03" });

    fireEvent.click(
      screen.getByRole("button", { name: "Edit result" }),
    );

    expect(screen.getByLabelText("Modified status")).toHaveValue(
      "partially_implemented",
    );

    expect(screen.getByLabelText("Modified explanation")).toHaveValue(
      pendingReview.explanation,
    );

    expect(submitReviewDecision).not.toHaveBeenCalled();
  });


  it("submits the modified result with trimmed text", async () => {
    submitReviewDecision.mockResolvedValueOnce({
      result_id: pendingReview.result_id,
      outcome: "modified",
      comment: "Corrected after checking the configuration.",
      message: "Review decision received successfully.",
    });

    render(<ExpertReviewWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "PR.AA-03" });

    fireEvent.click(
      screen.getByRole("button", { name: "Edit result" }),
    );

    fireEvent.change(screen.getByLabelText("Modified status"), {
      target: { value: "not_implemented" },
    });

    fireEvent.change(screen.getByLabelText("Modified explanation"), {
      target: { value: "  MFA is not enabled for privileged accounts.  " },
    });

    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: {
        value: "  Corrected after checking the configuration.  ",
      },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Submit modified result" }),
    );

    await waitFor(() => {
      expect(submitReviewDecision).toHaveBeenCalledWith(
        pendingReview.result_id,
        "modified",
        "Corrected after checking the configuration.",
        "test-token",
        {
          control_status: "not_implemented",
          explanation: "MFA is not enabled for privileged accounts.",
        },
      );
    });

    expect(
      await screen.findByRole("heading", {
        name: "Review queue complete",
      }),
    ).toBeInTheDocument();
  });


  it("requires a non-blank modified explanation", async () => {
    render(<ExpertReviewWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "PR.AA-03" });

    fireEvent.click(
      screen.getByRole("button", { name: "Edit result" }),
    );

    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: { value: "The result needs correction." },
    });

    fireEvent.change(screen.getByLabelText("Modified explanation"), {
      target: { value: "   " },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Submit modified result" }),
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "An explanation is required for a modified result.",
    );

    expect(submitReviewDecision).not.toHaveBeenCalled();
  });


  it.each([
    [
      "not_applicable",
      "Justification for not applicable",
      "A justification is required for not applicable.",
      "justification",
    ],
    [
      "not_assessed",
      "Reason for not assessed",
      "A reason is required for not assessed.",
      "not_assessed_reason",
    ],
  ])(
    "requires and submits the additional reason for %s",
    async (status, fieldLabel, errorMessage, payloadField) => {
      submitReviewDecision.mockResolvedValueOnce({
        result_id: pendingReview.result_id,
        outcome: "modified",
        comment: "Updated after review.",
        message: "Review decision received successfully.",
      });

      render(<ExpertReviewWorkspace accessToken="test-token" />);

      await screen.findByRole("heading", { name: "PR.AA-03" });

      fireEvent.click(
        screen.getByRole("button", { name: "Edit result" }),
      );

      fireEvent.change(screen.getByLabelText("Modified status"), {
        target: { value: status },
      });

      fireEvent.change(screen.getByLabelText("Review comment"), {
        target: { value: "Updated after review." },
      });

      fireEvent.change(screen.getByLabelText(fieldLabel), {
        target: { value: "   " },
      });

      fireEvent.click(
        screen.getByRole("button", { name: "Submit modified result" }),
      );

      expect(screen.getByRole("alert")).toHaveTextContent(errorMessage);
      expect(submitReviewDecision).not.toHaveBeenCalled();

      fireEvent.change(screen.getByLabelText(fieldLabel), {
        target: { value: "  Reason confirmed by the consultant.  " },
      });

      fireEvent.click(
        screen.getByRole("button", { name: "Submit modified result" }),
      );

      await waitFor(() => {
        expect(submitReviewDecision).toHaveBeenCalledWith(
          pendingReview.result_id,
          "modified",
          "Updated after review.",
          "test-token",
          {
            control_status: status,
            explanation: pendingReview.explanation,
            [payloadField]: "Reason confirmed by the consultant.",
          },
        );
      });

      await screen.findByRole("heading", {
        name: "Review queue complete",
      });
    },
  );


  it("preserves the edited fields when submission fails", async () => {
    submitReviewDecision.mockRejectedValueOnce(
      new Error("Unable to submit review."),
    );

    render(<ExpertReviewWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "PR.AA-03" });

    fireEvent.click(
      screen.getByRole("button", { name: "Edit result" }),
    );

    fireEvent.change(screen.getByLabelText("Modified status"), {
      target: { value: "not_implemented" },
    });

    fireEvent.change(screen.getByLabelText("Modified explanation"), {
      target: { value: "No MFA configuration was found." },
    });

    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: { value: "Configuration checked." },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Submit modified result" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to submit review.",
    );

    expect(screen.getByLabelText("Modified status")).toHaveValue(
      "not_implemented",
    );

    expect(screen.getByLabelText("Modified explanation")).toHaveValue(
      "No MFA configuration was found.",
    );

    expect(screen.getByLabelText("Review comment")).toHaveValue(
      "Configuration checked.",
    );

    expect(
      screen.getByRole("button", { name: "Submit modified result" }),
    ).toBeEnabled();
  });


  it("cancels editing without submitting a decision", async () => {
    render(<ExpertReviewWorkspace accessToken="test-token" />);

    await screen.findByRole("heading", { name: "PR.AA-03" });

    fireEvent.click(
      screen.getByRole("button", { name: "Edit result" }),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Cancel editing" }),
    );

    expect(
      screen.queryByLabelText("Modified status"),
    ).not.toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: "Accept" }),
    ).toBeEnabled();

    expect(submitReviewDecision).not.toHaveBeenCalled();
  });
});