import { useEffect, useRef, useState } from "react";

import { getInterview, submitInterviewTurn } from "./api.js";
import { describeInterviewError, isRetryableInterviewError } from "./errors.js";

const MAX_ANSWER_LENGTH = 10000;

const TURN_TYPE_LABELS = {
  follow_up: "Follow-up",
  clarification: "Clarification",
  evidence_request: "Evidence request",
  contradiction_prompt: "Clarifying a difference",
  summary: "Summary",
};

function newRequestId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
}

function mergeTurns(current, incoming) {
  const byId = new Map(current.map((turn) => [turn.id, turn]));
  incoming.filter(Boolean).forEach((turn) => byId.set(turn.id, turn));
  return Array.from(byId.values()).sort((a, b) => a.sequence_no - b.sequence_no);
}

export default function InterviewConversation({ organizationId, assessmentId, interview, accessToken }) {
  const session = interview.session;
  const [turns, setTurns] = useState(() => mergeTurns([], interview.turns || []));
  const [closed, setClosed] = useState(Boolean(session?.closed));
  const [answer, setAnswer] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [canRetry, setCanRetry] = useState(false);
  const accessTokenRef = useRef(accessToken);
  const pendingRequestRef = useRef(null);
  const sendingRef = useRef(false);
  const activeRef = useRef(true);
  const endRef = useRef(null);
  const answerRef = useRef(null);

  useEffect(() => {
    accessTokenRef.current = accessToken;
  }, [accessToken]);

  useEffect(() => {
    activeRef.current = true;
    return () => {
      activeRef.current = false;
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [turns.length]);

  const latestTurn = turns[turns.length - 1];
  const latestAgentTurn = [...turns].reverse().find((turn) => turn.speaker === "agent");
  const awaitingAnswer = !closed && latestTurn?.speaker === "agent";

  useEffect(() => {
    if (awaitingAnswer && !isSending) {
      answerRef.current?.focus();
    }
  }, [awaitingAnswer, isSending, turns.length]);

  async function submit(event) {
    event.preventDefault();
    const content = answer.trim();
    if (!content || !awaitingAnswer || sendingRef.current) {
      return;
    }

    sendingRef.current = true;
    setIsSending(true);
    setError("");
    setCanRetry(false);

    const pending = pendingRequestRef.current?.content === content
      ? pendingRequestRef.current
      : { content, id: newRequestId() };
    pendingRequestRef.current = pending;

    try {
      const receipt = await submitInterviewTurn(
        organizationId,
        assessmentId,
        {
          session_id: session.id,
          content,
          question_id: latestAgentTurn.question_id ?? null,
          replies_to_turn_id: latestAgentTurn.id,
          client_request_id: pending.id,
        },
        accessTokenRef.current,
      );
      if (!activeRef.current) {
        return;
      }
      pendingRequestRef.current = null;
      setAnswer("");

      if (receipt.idempotent_replay) {
        try {
          const refreshed = await getInterview(organizationId, assessmentId, session.id, accessTokenRef.current);
          if (!activeRef.current) {
            return;
          }
          setTurns(mergeTurns([], refreshed.turns || []));
          setClosed(Boolean(refreshed.session?.closed));
        } catch {
          if (!activeRef.current) {
            return;
          }
          setTurns((current) => mergeTurns(current, [receipt.turn]));
          setError("Your answer was saved, but the conversation could not be refreshed. Reopen the interview to continue.");
        }
      } else {
        setTurns((current) => mergeTurns(current, [receipt.turn, ...(receipt.agent_turns || [])]));
        setClosed(Boolean(receipt.session_closed));
      }
    } catch (caught) {
      if (!activeRef.current) {
        return;
      }
      setError(describeInterviewError(caught));
      setCanRetry(isRetryableInterviewError(caught));
    } finally {
      sendingRef.current = false;
      if (activeRef.current) {
        setIsSending(false);
      }
    }
  }

  const scopeCount = interview.in_scope_controls?.length;

  return (
    <section className="interview-conversation" aria-label="Interview">
      <header className="interview-header">
        <div>
          <p className="eyebrow">INTERVIEW</p>
          <h2>{interview.assessment_title || "Assessment interview"}</h2>
        </div>
        {typeof scopeCount === "number" && (
          <span className="interview-scope">{scopeCount} {scopeCount === 1 ? "control" : "controls"} in scope</span>
        )}
      </header>

      <ol className="interview-turns" role="log" aria-label="Interview conversation" aria-live="polite">
        {turns.map((turn) => (
          <li key={turn.id} className={`interview-turn is-${turn.speaker === "agent" ? "agent" : "participant"}`}>
            <div className="interview-turn-meta">
              <span className="interview-speaker">{turn.speaker === "agent" ? "Assistant" : "You"}</span>
              {turn.speaker === "agent" && TURN_TYPE_LABELS[turn.turn_type] && (
                <span className="interview-turn-type">{TURN_TYPE_LABELS[turn.turn_type]}</span>
              )}
            </div>
            <p>{turn.content}</p>
          </li>
        ))}
        <li ref={endRef} className="interview-end" aria-hidden="true" />
      </ol>

      {isSending && (
        <p className="interview-status" role="status">The assistant is reviewing your answer…</p>
      )}
      {error && <p className="inline-error" role="alert">{error}</p>}

      {closed ? (
        <p className="interview-complete" role="status">
          The interview is complete. Your answers were saved and will go to an expert for review.
        </p>
      ) : (
        <form className="interview-form" onSubmit={submit}>
          <label htmlFor="interview-answer">Your answer</label>
          <textarea
            id="interview-answer"
            ref={answerRef}
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            maxLength={MAX_ANSWER_LENGTH}
            rows={5}
            disabled={isSending || !awaitingAnswer}
            placeholder={awaitingAnswer ? "Describe how this works in your organization." : ""}
          />
          <div className="interview-form-footer">
            <span>{answer.length} / {MAX_ANSWER_LENGTH}</span>
            <button
              className="primary-button"
              type="submit"
              disabled={isSending || !awaitingAnswer || !answer.trim()}
            >
              {isSending ? "Sending…" : canRetry ? "Retry sending" : "Send answer"}
            </button>
          </div>
          {!awaitingAnswer && (
            <p className="interview-hint">There is no open question. Reopen the interview to continue.</p>
          )}
        </form>
      )}
    </section>
  );
}
