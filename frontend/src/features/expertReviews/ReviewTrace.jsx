import { useEffect, useRef, useState } from "react";

import { getReviewTrace } from "./api.js";

const DECISION_LABELS = {
  answer_interpreted: "Answer interpreted",
  evidence_requested: "Evidence requested",
  evidence_extracted: "Evidence extracted",
  evidence_validated: "Evidence validated",
  mapping_assigned: "Mapping assigned",
  status_assessed: "Status assessed",
  maturity_assessed: "Maturity assessed",
  contradiction_detected: "Contradiction detected",
  finding_generated: "Finding generated",
  human_review: "Expert review",
};

const ACTOR_LABELS = {
  agent: "AI agent",
  aligo_consultant: "Aligo consultant",
  assessed_org_representative: "Organization representative",
};

const SOURCE_LABELS = {
  interview_turn: "Interview answer",
  document_span: "Document",
  tenant_configuration: "Tenant configuration",
  prior_phase_evidence: "Prior phase evidence",
};

function label(labels, value) {
  return labels[value] || String(value).replaceAll("_", " ");
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown time";
  }
  return `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function describeError(error) {
  if (error?.status === 403) {
    return "Only administrators and consultants can view reasoning traces.";
  }
  if (error?.status === 404) {
    return "This result was not found, or you do not have access to it.";
  }
  return "Unable to load the reasoning trace. This does not mean that no trace exists.";
}

function StepOutcome({ step }) {
  if (step.decision_type === "human_review" && step.review_outcome) {
    return <p><strong>Review outcome:</strong> {step.review_outcome}</p>;
  }
  if (typeof step.output?.status === "string") {
    return <p><strong>Status:</strong> {label({}, step.output.status)}</p>;
  }
  return null;
}

function TraceStep({ step, isResultDecision }) {
  const sources = step.sources || [];
  return (
    <li className={`review-trace-step${isResultDecision ? " is-result-decision" : ""}`}>
      <div className="review-trace-step-heading">
        <strong>{label(DECISION_LABELS, step.decision_type)}</strong>
        {isResultDecision && <span className="review-trace-badge">Decision behind this result</span>}
      </div>
      <p className="review-trace-meta">
        {`${formatTime(step.created_at)} · ${label(ACTOR_LABELS, step.actor_type)}`}
        {step.confidence != null && ` · confidence ${Math.round(step.confidence * 100)}%`}
        {step.prompt_id && ` · ${step.prompt_id}${step.prompt_version ? ` v${step.prompt_version}` : ""}`}
        {step.model_name && ` · ${step.model_name}`}
        {` · KB ${step.kb_version}`}
      </p>
      <StepOutcome step={step} />
      <p>{step.rationale}</p>
      {(step.fallback_used || step.requires_human_review) && (
        <p className="review-trace-flags">
          {step.fallback_used && "Fallback used (the model was unavailable or its output was invalid). "}
          {step.requires_human_review && "Flagged for human review."}
        </p>
      )}
      {sources.length === 0 ? (
        <p>No source references were recorded for this step.</p>
      ) : (
        <ul className="review-trace-sources" aria-label="Source references">
          {sources.map((source, index) => (
            <li key={`${source.type}-${source.ref}-${index}`}>
              <span>{label(SOURCE_LABELS, source.type)}: </span>
              <span className="review-source-reference">{source.ref}</span>
              {source.excerpt && <blockquote>{source.excerpt}</blockquote>}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

// The reasoning steps behind one result, inside the Expert reviews screen (HU-25, AGRC-60).
export default function ReviewTrace({ resultId, accessToken, sessionId }) {
  const [isOpen, setIsOpen] = useState(false);
  const [response, setResponse] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const accessTokenRef = useRef(accessToken);
  const sessionKey = sessionId ?? accessToken;

  useEffect(() => {
    accessTokenRef.current = accessToken;
  }, [accessToken]);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    let active = true;
    setResponse(null);

    getReviewTrace(resultId, accessTokenRef.current)
      .then((trace) => {
        if (active) setResponse({ resultId, sessionKey, trace });
      })
      .catch((error) => {
        if (active) setResponse({ resultId, sessionKey, error });
      });

    return () => {
      active = false;
    };
  }, [isOpen, resultId, sessionKey, attempt]);

  // Never show the trace of a different result or session, even for one render.
  const current =
    response?.resultId === resultId && response?.sessionKey === sessionKey ? response : null;

  let body = null;
  if (isOpen && !current) {
    body = <p>Loading reasoning trace...</p>;
  } else if (isOpen && current.error) {
    body = (
      <>
        <p role="alert">{describeError(current.error)}</p>
        {current.error?.status !== 403 && current.error?.status !== 404 && (
          <button className="secondary-button" type="button" onClick={() => setAttempt((count) => count + 1)}>
            Retry trace
          </button>
        )}
      </>
    );
  } else if (isOpen) {
    const trace = current.trace;
    const steps = trace.steps || [];
    const hasResultDecision = steps.some((step) => step.id === trace.result_trace_id);
    body = (
      <>
        <dl className="review-trace-context">
          <div><dt>Organization</dt><dd>{trace.organization_name}</dd></div>
          <div><dt>Assessment</dt><dd>{trace.assessment_title}</dd></div>
          <div><dt>Control</dt><dd>{`${trace.control_code} · ${trace.control_title}`}</dd></div>
          <div>
            <dt>Result version</dt>
            <dd>{`${trace.result_version} (${trace.result_author === "agent" ? "AI draft" : "Consultant version"})`}</dd>
          </div>
        </dl>
        {!trace.result_trace_id && (
          <p role="status">No recorded decision is linked to this result version.</p>
        )}
        {trace.result_trace_id && !hasResultDecision && (
          <p role="alert">The decision linked to this result could not be found in the trace.</p>
        )}
        {steps.length === 0 ? (
          <p>No reasoning trace is recorded for this control.</p>
        ) : (
          <ol className="review-trace-steps" aria-label="Reasoning steps">
            {steps.map((step) => (
              <TraceStep key={step.id} step={step} isResultDecision={step.id === trace.result_trace_id} />
            ))}
          </ol>
        )}
      </>
    );
  }

  return (
    <div className="review-section review-trace">
      <h3>Reasoning trace</h3>
      <button
        className="secondary-button"
        type="button"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((open) => !open)}
      >
        {isOpen ? "Hide reasoning trace" : "Show reasoning trace"}
      </button>
      {body}
    </div>
  );
}
