import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client.js";
import { getReviewTrace } from "./api.js";
import ReviewTrace from "./ReviewTrace.jsx";

vi.mock("./api.js", () => ({
  getReviewTrace: vi.fn(),
}));

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  promise.catch(() => {});
  return { promise, resolve, reject };
}

function step(id, changes = {}) {
  return {
    id,
    created_at: "2026-10-24T10:00:00Z",
    organization_id: "org-1",
    assessment_id: "assess-1",
    decision_type: "status_assessed",
    control_ids: ["PR.AA-03"],
    sources: [{ type: "interview_turn", ref: "interview_turn:turn-7", excerpt: "Only admins use MFA." }],
    actor_type: "agent",
    actor_user_id: null,
    model_name: "llama3.1:8b",
    prompt_id: "rule:partial",
    prompt_version: "0.3.0",
    kb_version: "demo-0.2",
    output: { status: "partially_implemented" },
    rationale: "MFA covers administrators only.",
    confidence: 0.72,
    requires_human_review: false,
    fallback_used: false,
    reviews_trace_id: null,
    review_outcome: null,
    ...changes,
  };
}

function traceFor(resultId, changes = {}) {
  return {
    result_id: resultId,
    organization_id: "org-1",
    organization_name: "Halverston Community Bank",
    assessment_id: "assess-1",
    assessment_title: "Q4 identity review",
    control_code: "PR.AA-03",
    control_title: "Users, services, and hardware are authenticated",
    result_version: 1,
    result_author: "agent",
    result_trace_id: "trace-2",
    steps: [
      step("trace-1", {
        decision_type: "answer_interpreted",
        output: { intent: "partial" },
        rationale: "The answer mentions MFA for administrators only.",
        fallback_used: true,
        requires_human_review: true,
      }),
      step("trace-2"),
    ],
    ...changes,
  };
}

function open() {
  fireEvent.click(screen.getByRole("button", { name: "Show reasoning trace" }));
}

describe("ReviewTrace", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    getReviewTrace.mockImplementation((resultId) => Promise.resolve(traceFor(resultId)));
  });

  it("stays collapsed and loads nothing until the reviewer opens it", () => {
    render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);

    expect(screen.getByRole("button", { name: "Show reasoning trace" })).toHaveAttribute("aria-expanded", "false");
    expect(getReviewTrace).not.toHaveBeenCalled();
  });

  it("shows the result context and the steps with the result's own decision highlighted", async () => {
    render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);

    open();

    const steps = (await screen.findByRole("list", { name: "Reasoning steps" })).querySelectorAll(".review-trace-step");
    expect(getReviewTrace).toHaveBeenCalledWith("result-1", "token-a");
    expect(screen.getByText("Halverston Community Bank")).toBeInTheDocument();
    expect(screen.getByText("Q4 identity review")).toBeInTheDocument();
    expect(screen.getByText("PR.AA-03 · Users, services, and hardware are authenticated")).toBeInTheDocument();
    expect(screen.getByText("1 (AI draft)")).toBeInTheDocument();
    expect(steps).toHaveLength(2);
    expect(within(steps[0]).getByText("Answer interpreted")).toBeInTheDocument();
    expect(within(steps[0]).queryByText("Decision behind this result")).not.toBeInTheDocument();
    expect(within(steps[0]).getByText(/Fallback used/)).toBeInTheDocument();
    expect(within(steps[1]).getByText("Status assessed")).toBeInTheDocument();
    expect(within(steps[1]).getByText("Decision behind this result")).toBeInTheDocument();
    expect(within(steps[1]).getByText("partially implemented")).toBeInTheDocument();
    expect(within(steps[1]).getByText("interview_turn:turn-7")).toBeInTheDocument();
    expect(within(steps[1]).getByText("Only admins use MFA.")).toBeInTheDocument();
    expect(within(steps[1]).getByText(/2026-10-24 10:00 UTC · AI agent · confidence 72% · rule:partial v0.3.0/)).toBeInTheDocument();
  });

  it("highlights the decision that belongs to the result, not the latest step", async () => {
    getReviewTrace.mockResolvedValue(
      traceFor("result-1", {
        result_trace_id: "trace-1",
        steps: [step("trace-1"), step("trace-2", { decision_type: "human_review", review_outcome: "accepted", actor_type: "aligo_consultant", confidence: null })],
      }),
    );
    render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);

    open();

    const steps = (await screen.findByRole("list", { name: "Reasoning steps" })).querySelectorAll(".review-trace-step");
    expect(steps[0]).toHaveClass("is-result-decision");
    expect(steps[1]).not.toHaveClass("is-result-decision");
    expect(within(steps[1]).getByText("Expert review")).toBeInTheDocument();
    expect(within(steps[1]).getByText("accepted")).toBeInTheDocument();
  });

  it("says clearly when no decision is linked and does not invent one", async () => {
    getReviewTrace.mockResolvedValue(traceFor("result-1", { result_trace_id: null, steps: [] }));
    render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);

    open();

    expect(await screen.findByText("No recorded decision is linked to this result version.")).toBeInTheDocument();
    expect(screen.getByText("No reasoning trace is recorded for this control.")).toBeInTheDocument();
    expect(screen.queryByText("Decision behind this result")).not.toBeInTheDocument();
  });

  it("warns when the linked decision is missing from the steps", async () => {
    getReviewTrace.mockResolvedValue(traceFor("result-1", { result_trace_id: "trace-9" }));
    render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);

    open();

    expect(await screen.findByRole("alert")).toHaveTextContent("could not be found in the trace");
  });

  it("shows an unavailable state on failure and retries with the latest token", async () => {
    getReviewTrace.mockRejectedValueOnce(new Error("Network down"));
    const { rerender } = render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);

    open();

    expect(await screen.findByRole("alert")).toHaveTextContent("This does not mean that no trace exists.");
    expect(screen.queryByText("Halverston Community Bank")).not.toBeInTheDocument();

    rerender(<ReviewTrace resultId="result-1" accessToken="token-b" sessionId="user-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Retry trace" }));

    expect(await screen.findByText("Halverston Community Bank")).toBeInTheDocument();
    expect(getReviewTrace).toHaveBeenLastCalledWith("result-1", "token-b");
  });

  it("explains a denied request without trace data or a retry", async () => {
    getReviewTrace.mockRejectedValue(new ApiError(403, { detail: "Administrator or consultant access required." }));
    render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);

    open();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only administrators and consultants can view reasoning traces.",
    );
    expect(screen.queryByRole("button", { name: "Retry trace" })).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Reasoning steps" })).not.toBeInTheDocument();
  });

  it("keeps the open panel on token refresh without reloading", async () => {
    const { rerender } = render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);
    open();
    await screen.findByText("Halverston Community Bank");

    rerender(<ReviewTrace resultId="result-1" accessToken="token-b" sessionId="user-1" />);

    expect(screen.getByText("Halverston Community Bank")).toBeInTheDocument();
    expect(getReviewTrace).toHaveBeenCalledTimes(1);
  });

  it("hides the old trace at once and ignores its late response after the result changes", async () => {
    const slow = deferred();
    getReviewTrace.mockImplementation((resultId) =>
      resultId === "result-1" ? slow.promise : Promise.resolve(traceFor("result-2", { assessment_title: "Second assessment" })),
    );
    const { rerender } = render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);
    open();

    rerender(<ReviewTrace resultId="result-2" accessToken="token-a" sessionId="user-1" />);
    expect(await screen.findByText("Second assessment")).toBeInTheDocument();

    await act(async () => {
      slow.resolve(traceFor("result-1", { assessment_title: "First assessment" }));
    });

    expect(screen.getByText("Second assessment")).toBeInTheDocument();
    expect(screen.queryByText("First assessment")).not.toBeInTheDocument();
  });

  it("reloads for a new session", async () => {
    const { rerender } = render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);
    open();
    await screen.findByText("Halverston Community Bank");

    rerender(<ReviewTrace resultId="result-1" accessToken="token-c" sessionId="user-2" />);

    await waitFor(() => expect(getReviewTrace).toHaveBeenCalledTimes(2));
    expect(getReviewTrace).toHaveBeenLastCalledWith("result-1", "token-c");
  });

  it("ignores a response that arrives after unmount", async () => {
    const slow = deferred();
    getReviewTrace.mockReturnValue(slow.promise);
    const { unmount } = render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);
    open();

    unmount();
    await act(async () => {
      slow.resolve(traceFor("result-1"));
    });

    expect(getReviewTrace).toHaveBeenCalledTimes(1);
  });

  it("can be hidden again", async () => {
    render(<ReviewTrace resultId="result-1" accessToken="token-a" sessionId="user-1" />);
    open();
    await screen.findByText("Halverston Community Bank");

    fireEvent.click(screen.getByRole("button", { name: "Hide reasoning trace" }));

    expect(screen.queryByText("Halverston Community Bank")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show reasoning trace" })).toHaveAttribute("aria-expanded", "false");
  });
});
