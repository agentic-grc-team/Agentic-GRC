import { useEffect, useRef, useState } from "react";

import { listAssessments } from "../assessments/api.js";
import { listOrganizations } from "../organizations/api.js";
import { openInterview } from "./api.js";
import InterviewConversation from "./InterviewConversation.jsx";
import { describeInterviewError } from "./errors.js";
import "./InterviewWorkspace.css";

const STATUS_LABELS = {
  draft: "Draft",
  in_progress: "In progress",
  in_review: "In review",
  completed: "Completed",
  archived: "Archived",
};

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

export default function InterviewWorkspace({
  accessToken,
  sessionId,
  initialOrganizationId = "",
  initialAssessmentId = "",
  onOrganizationChange,
}) {
  const accessTokenRef = useRef(accessToken);
  const startSeqRef = useRef(0);
  const [organizations, setOrganizations] = useState([]);
  const [organizationsLoaded, setOrganizationsLoaded] = useState(false);
  const [organizationId, setOrganizationId] = useState(initialOrganizationId);
  const [assessments, setAssessments] = useState([]);
  const [assessmentsLoaded, setAssessmentsLoaded] = useState(false);
  const [assessmentId, setAssessmentId] = useState(initialAssessmentId);
  const [interview, setInterview] = useState(null);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    accessTokenRef.current = accessToken;
  }, [accessToken]);

  useEffect(() => {
    let active = true;
    setOrganizationsLoaded(false);
    setError("");
    listOrganizations(accessTokenRef.current, { activeMembershipsOnly: true })
      .then((items) => {
        if (!active) {
          return;
        }
        setOrganizations(items);
        setOrganizationId((current) => (
          items.some((item) => item.id === current) ? current : items.length === 1 ? items[0].id : ""
        ));
      })
      .catch((caught) => {
        if (active) {
          setOrganizations([]);
          setError(describeInterviewError(caught));
        }
      })
      .finally(() => {
        if (active) {
          setOrganizationsLoaded(true);
        }
      });
    return () => {
      active = false;
    };
  }, [sessionId]);

  useEffect(() => {
    if (!organizationId) {
      setAssessments([]);
      setAssessmentsLoaded(false);
      return undefined;
    }
    let active = true;
    setAssessmentsLoaded(false);
    listAssessments(organizationId, accessTokenRef.current)
      .then((items) => {
        if (!active) {
          return;
        }
        setAssessments(items);
        setAssessmentId((current) => (
          items.some((item) => item.id === current) ? current : items.length === 1 ? items[0].id : ""
        ));
      })
      .catch((caught) => {
        if (active) {
          setAssessments([]);
          setAssessmentId("");
          setError(describeInterviewError(caught));
        }
      })
      .finally(() => {
        if (active) {
          setAssessmentsLoaded(true);
        }
      });
    return () => {
      active = false;
    };
  }, [organizationId, sessionId]);

  useEffect(() => {
    startSeqRef.current += 1;
    setInterview(null);
    setIsStarting(false);
  }, [organizationId, assessmentId]);

  function changeOrganization(event) {
    const value = event.target.value;
    setError("");
    setOrganizationId(value);
    setAssessmentId("");
    onOrganizationChange?.(value);
  }

  function changeAssessment(event) {
    setError("");
    setAssessmentId(event.target.value);
  }

  async function startInterview() {
    if (!organizationId || !assessmentId || isStarting) {
      return;
    }
    const seq = startSeqRef.current + 1;
    startSeqRef.current = seq;
    setIsStarting(true);
    setError("");
    try {
      const data = await openInterview(organizationId, assessmentId, accessTokenRef.current);
      if (seq !== startSeqRef.current) {
        return;
      }
      if (!data?.session) {
        setError("The interview could not be started. Try again.");
        return;
      }
      setInterview({ organizationId, assessmentId, data, openedAt: seq });
    } catch (caught) {
      if (seq === startSeqRef.current) {
        setError(describeInterviewError(caught));
      }
    } finally {
      if (seq === startSeqRef.current) {
        setIsStarting(false);
      }
    }
  }

  const selectedAssessment = assessments.find((item) => item.id === assessmentId);
  const canStart = Boolean(selectedAssessment) && selectedAssessment.status === "in_progress" && !isStarting;

  return (
    <section className="interview-workspace">
      <p className="eyebrow">ASSESSMENT INTERVIEW</p>
      <h1>Interview</h1>
      <p className="interview-intro">
        Answer the assistant’s questions about your organization’s security practices. Your answers are saved
        as you go, and you can come back to continue where you left off.
      </p>

      {error && <p className="inline-error" role="alert">{error}</p>}

      <div className="interview-pickers">
        <label>
          Organization
          <select value={organizationId} onChange={changeOrganization} disabled={!organizationsLoaded}>
            <option value="">Select an organization</option>
            {organizations.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
        </label>
        <label>
          Assessment
          <select
            value={assessmentId}
            onChange={changeAssessment}
            disabled={!organizationId || !assessmentsLoaded}
          >
            <option value="">Select an assessment</option>
            {assessments.map((item) => (
              <option key={item.id} value={item.id}>{item.title} · {statusLabel(item.status)}</option>
            ))}
          </select>
        </label>
        <button className="primary-button" type="button" onClick={startInterview} disabled={!canStart}>
          {isStarting ? "Opening…" : "Start or resume interview"}
        </button>
      </div>

      {organizationsLoaded && !error && organizations.length === 0 && (
        <p className="interview-hint">You are not a member of any organization yet.</p>
      )}
      {organizationId && assessmentsLoaded && !error && assessments.length === 0 && (
        <p className="interview-hint">This organization has no assessments yet.</p>
      )}
      {selectedAssessment && selectedAssessment.status !== "in_progress" && (
        <p className="interview-hint">Only assessments that are in progress accept interview answers.</p>
      )}

      {interview && (
        <InterviewConversation
          key={`${interview.organizationId}:${interview.assessmentId}:${interview.openedAt}`}
          organizationId={interview.organizationId}
          assessmentId={interview.assessmentId}
          interview={interview.data}
          accessToken={accessToken}
        />
      )}
    </section>
  );
}
