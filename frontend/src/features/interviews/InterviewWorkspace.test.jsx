import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client.js";
import { listAssessments } from "../assessments/api.js";
import { listOrganizations } from "../organizations/api.js";
import { getInterview, openInterview, submitInterviewTurn } from "./api.js";
import InterviewWorkspace from "./InterviewWorkspace.jsx";

vi.mock("./api.js", () => ({
  openInterview: vi.fn(),
  getInterview: vi.fn(),
  submitInterviewTurn: vi.fn(),
}));
vi.mock("../assessments/api.js", () => ({ listAssessments: vi.fn() }));
vi.mock("../organizations/api.js", () => ({ listOrganizations: vi.fn() }));

const organizations = [{ id: "org-1", name: "Acme Corp" }];
const assessments = [
  { id: "assessment-1", title: "NIST CSF baseline", status: "in_progress" },
  { id: "assessment-2", title: "Old assessment", status: "completed" },
];

function turn(overrides) {
  return {
    id: "turn-1",
    sequence_no: 1,
    speaker: "agent",
    participant_id: null,
    turn_type: "question",
    question_id: "question-1",
    replies_to_turn_id: null,
    content: "How do you manage user access?",
    ...overrides,
  };
}

function interview(overrides = {}) {
  return {
    organization_id: "org-1",
    organization_name: "Acme Corp",
    assessment_id: "assessment-1",
    assessment_title: "NIST CSF baseline",
    assessment_status: "in_progress",
    participant_id: "participant-1",
    session: { id: "session-1", closed: false },
    turns: [turn()],
    in_scope_controls: [
      { id: "control-1", code: "PR.AA-03", title: "Authentication" },
      { id: "control-2", code: "PR.AA-05", title: "Access permissions" },
    ],
    draft_results: [],
    resumed: false,
    ...overrides,
  };
}

function receipt(overrides = {}) {
  return {
    turn: turn({
      id: "turn-2",
      sequence_no: 2,
      speaker: "participant",
      turn_type: "answer",
      replies_to_turn_id: "turn-1",
      content: "We use Okta with MFA.",
    }),
    agent_turns: [
      turn({
        id: "turn-3",
        sequence_no: 3,
        turn_type: "follow_up",
        question_id: "question-2",
        content: "Who reviews access rights?",
      }),
    ],
    draft_results: [],
    session_closed: false,
    idempotent_replay: false,
    ...overrides,
  };
}

async function openSelectedInterview() {
  const button = await screen.findByRole("button", { name: "Start or resume interview" });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  return screen.findByRole("log", { name: "Interview conversation" });
}

function answerBox() {
  return screen.getByLabelText("Your answer");
}

function sendAnswer(text) {
  fireEvent.change(answerBox(), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /Send answer|Retry sending/ }));
}

function renderWorkspace(props = {}) {
  return render(<InterviewWorkspace accessToken="token-a" sessionId="user-a" {...props} />);
}

describe("InterviewWorkspace", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    listOrganizations.mockResolvedValue(organizations);
    listAssessments.mockResolvedValue(assessments);
    openInterview.mockResolvedValue(interview());
    getInterview.mockResolvedValue(interview());
    submitInterviewTurn.mockResolvedValue(receipt());
  });

  it("selects the single organization and assessment and shows the first question", async () => {
    renderWorkspace({ initialAssessmentId: "assessment-1" });

    const log = await openSelectedInterview();

    expect(openInterview).toHaveBeenCalledWith("org-1", "assessment-1", "token-a");
    expect(log).toHaveTextContent("How do you manage user access?");
    expect(screen.getByText("2 controls in scope")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "NIST CSF baseline" })).toBeInTheDocument();
  });

  it("only allows starting an interview for an assessment in progress", async () => {
    renderWorkspace();

    const assessmentSelect = await screen.findByLabelText("Assessment");
    await waitFor(() => expect(assessmentSelect).toBeEnabled());
    fireEvent.change(assessmentSelect, { target: { value: "assessment-2" } });

    expect(screen.getByRole("button", { name: "Start or resume interview" })).toBeDisabled();
    expect(screen.getByText(/Only assessments that are in progress/)).toBeInTheDocument();
  });

  it("saves an answer with the question it replies to and shows the follow-up", async () => {
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();

    sendAnswer("  We use Okta with MFA.  ");

    const log = screen.getByRole("log", { name: "Interview conversation" });
    await waitFor(() => expect(log).toHaveTextContent("Who reviews access rights?"));
    expect(log).toHaveTextContent("We use Okta with MFA.");
    expect(submitInterviewTurn).toHaveBeenCalledTimes(1);
    const [organizationId, assessmentId, payload, token] = submitInterviewTurn.mock.calls[0];
    expect([organizationId, assessmentId, token]).toEqual(["org-1", "assessment-1", "token-a"]);
    expect(payload).toMatchObject({
      session_id: "session-1",
      content: "We use Okta with MFA.",
      question_id: "question-1",
      replies_to_turn_id: "turn-1",
    });
    expect(payload.client_request_id).toEqual(expect.any(String));
    expect(answerBox()).toHaveValue("");
    expect(screen.getByText("Follow-up")).toBeInTheDocument();
  });

  it("answers the latest agent turn on the next round", async () => {
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();
    sendAnswer("We use Okta with MFA.");
    await screen.findByText("Who reviews access rights?");

    sendAnswer("The IT manager, quarterly.");

    await waitFor(() => expect(submitInterviewTurn).toHaveBeenCalledTimes(2));
    expect(submitInterviewTurn.mock.calls[1][2]).toMatchObject({
      question_id: "question-2",
      replies_to_turn_id: "turn-3",
    });
    expect(submitInterviewTurn.mock.calls[1][2].client_request_id)
      .not.toBe(submitInterviewTurn.mock.calls[0][2].client_request_id);
  });

  it("does not send a blank answer", async () => {
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();

    fireEvent.change(answerBox(), { target: { value: "   " } });

    expect(screen.getByRole("button", { name: "Send answer" })).toBeDisabled();
    expect(submitInterviewTurn).not.toHaveBeenCalled();
  });

  it("sends one request when the answer is submitted twice while saving", async () => {
    let resolveTurn;
    submitInterviewTurn.mockReturnValue(new Promise((resolve) => { resolveTurn = resolve; }));
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();

    fireEvent.change(answerBox(), { target: { value: "We use Okta with MFA." } });
    const form = answerBox().closest("form");
    fireEvent.submit(form);
    fireEvent.submit(form);

    expect(submitInterviewTurn).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent("reviewing your answer");
    expect(answerBox()).toBeDisabled();

    resolveTurn(receipt());
    await screen.findByText("Who reviews access rights?");
  });

  it("keeps the answer and retries with the same request id after a temporary failure", async () => {
    submitInterviewTurn
      .mockRejectedValueOnce(new ApiError(503, { detail: "Agent unavailable" }))
      .mockResolvedValueOnce(receipt());
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();

    sendAnswer("We use Okta with MFA.");

    expect(await screen.findByRole("alert")).toHaveTextContent("unavailable");
    expect(answerBox()).toHaveValue("We use Okta with MFA.");

    fireEvent.click(screen.getByRole("button", { name: "Retry sending" }));

    await screen.findByText("Who reviews access rights?");
    expect(submitInterviewTurn.mock.calls[1][2].client_request_id)
      .toBe(submitInterviewTurn.mock.calls[0][2].client_request_id);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("uses a new request id when the answer is edited after a failure", async () => {
    submitInterviewTurn
      .mockRejectedValueOnce(new ApiError(503, { detail: "Agent unavailable" }))
      .mockResolvedValueOnce(receipt());
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();

    sendAnswer("We use Okta.");
    await screen.findByRole("alert");
    sendAnswer("We use Okta with MFA.");

    await screen.findByText("Who reviews access rights?");
    expect(submitInterviewTurn.mock.calls[1][2].client_request_id)
      .not.toBe(submitInterviewTurn.mock.calls[0][2].client_request_id);
  });

  it("shows the API message when the answer is rejected", async () => {
    submitInterviewTurn.mockRejectedValue(
      new ApiError(409, { detail: "This question already has a result." }),
    );
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();

    sendAnswer("We use Okta with MFA.");

    expect(await screen.findByRole("alert")).toHaveTextContent("This question already has a result.");
    expect(screen.getByRole("button", { name: "Send answer" })).toBeEnabled();
  });

  it("reloads the transcript when the answer was already recorded", async () => {
    submitInterviewTurn.mockResolvedValue(receipt({ agent_turns: [], idempotent_replay: true }));
    getInterview.mockResolvedValue(interview({
      turns: [turn(), receipt().turn, receipt().agent_turns[0]],
    }));
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();

    sendAnswer("We use Okta with MFA.");

    await screen.findByText("Who reviews access rights?");
    expect(getInterview).toHaveBeenCalledWith("org-1", "assessment-1", "session-1", "token-a");
  });

  it("shows a completion message and no answer form when the interview ends", async () => {
    submitInterviewTurn.mockResolvedValue(receipt({ agent_turns: [], session_closed: true }));
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();

    sendAnswer("We use Okta with MFA.");

    expect(await screen.findByText(/The interview is complete/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Your answer")).not.toBeInTheDocument();
  });

  it("resumes a conversation in progress with the earlier answers", async () => {
    openInterview.mockResolvedValue(interview({
      resumed: true,
      turns: [turn(), receipt().turn, receipt().agent_turns[0]],
    }));
    renderWorkspace({ initialAssessmentId: "assessment-1" });

    const log = await openSelectedInterview();

    expect(log).toHaveTextContent("We use Okta with MFA.");
    expect(log).toHaveTextContent("Who reviews access rights?");
  });

  it("opens a finished interview read-only", async () => {
    openInterview.mockResolvedValue(interview({
      session: { id: "session-1", closed: true },
      turns: [turn(), receipt().turn],
    }));
    renderWorkspace({ initialAssessmentId: "assessment-1" });

    await openSelectedInterview();

    expect(screen.getByText(/The interview is complete/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Your answer")).not.toBeInTheDocument();
  });

  it("never shows draft results", async () => {
    openInterview.mockResolvedValue(interview({
      draft_results: [{ id: "result-1", control_code: "PR.AA-03", status: "not_implemented", explanation: "Secret draft" }],
    }));
    renderWorkspace({ initialAssessmentId: "assessment-1" });

    await openSelectedInterview();

    expect(screen.queryByText(/Secret draft/)).not.toBeInTheDocument();
    expect(screen.queryByText(/not_implemented/)).not.toBeInTheDocument();
  });

  it("shows why an interview cannot be opened", async () => {
    openInterview.mockRejectedValue(
      new ApiError(409, { detail: "This assessment has no in-scope controls." }),
    );
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    const button = await screen.findByRole("button", { name: "Start or resume interview" });
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);

    expect(await screen.findByRole("alert")).toHaveTextContent("This assessment has no in-scope controls.");
    expect(screen.queryByRole("log")).not.toBeInTheDocument();
  });

  it("ignores an interview that finishes opening after another assessment was chosen", async () => {
    let resolveOpen;
    openInterview.mockReturnValue(new Promise((resolve) => { resolveOpen = resolve; }));
    listAssessments.mockResolvedValue([
      assessments[0],
      { id: "assessment-3", title: "Second assessment", status: "in_progress" },
    ]);
    renderWorkspace({ initialAssessmentId: "assessment-1" });
    const button = await screen.findByRole("button", { name: "Start or resume interview" });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    fireEvent.change(screen.getByLabelText("Assessment"), { target: { value: "assessment-3" } });
    resolveOpen(interview());

    await waitFor(() => expect(screen.getByRole("button", { name: "Start or resume interview" })).toBeEnabled());
    expect(screen.queryByRole("log")).not.toBeInTheDocument();
  });

  it("keeps the conversation and uses the refreshed token after a token refresh", async () => {
    const view = renderWorkspace({ initialAssessmentId: "assessment-1" });
    await openSelectedInterview();
    fireEvent.change(answerBox(), { target: { value: "Half-written answer" } });

    view.rerender(<InterviewWorkspace accessToken="token-b" sessionId="user-a" />);

    expect(answerBox()).toHaveValue("Half-written answer");
    expect(listOrganizations).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
    await screen.findByText("Who reviews access rights?");
    expect(submitInterviewTurn.mock.calls[0][3]).toBe("token-b");
  });

  it("explains when the user has no organization", async () => {
    listOrganizations.mockResolvedValue([]);
    renderWorkspace();

    expect(await screen.findByText(/not a member of any organization/)).toBeInTheDocument();
  });

  it("shows an error when organizations cannot be loaded", async () => {
    listOrganizations.mockRejectedValue(new ApiError(401, { detail: "Unauthorized" }));
    renderWorkspace();

    expect(await screen.findByRole("alert")).toHaveTextContent("session has expired");
  });
});
