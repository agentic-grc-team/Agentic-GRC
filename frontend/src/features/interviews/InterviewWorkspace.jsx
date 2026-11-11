import { useEffect, useRef, useState } from "react";

import { listAssessments } from "../assessments/api.js";
import { assessmentStatusLabel } from "../assessments/statusLabels.js";
import { listOrganizations } from "../organizations/api.js";
import { getInterview, getKickoffStatus, openInterview } from "./api.js";
import InterviewConversation from "./InterviewConversation.jsx";
import { describeInterviewError } from "./errors.js";
import "./InterviewWorkspace.css";

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
  const [kickoffStatus, setKickoffStatus] = useState(null);
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
    if (organizationsLoaded) onOrganizationChange?.(organizationId);
  }, [organizationId, organizationsLoaded, onOrganizationChange]);

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

  const selectedAssessment = assessments.find((item) => item.id === assessmentId);
  const selectionKey = JSON.stringify([sessionId, organizationId, assessmentId]);
  const selectedSession = kickoffStatus?.key === selectionKey ? kickoffStatus : null;
  const canOpen = !isStarting && Boolean(
    selectedAssessment && selectedSession &&
    (selectedSession.session?.closed || selectedAssessment.status === "in_progress")
  );

  useEffect(() => {
    if (!organizationId || !assessmentId) return undefined;

    setKickoffStatus(null);
    let active = true;
    getKickoffStatus(organizationId, assessmentId, accessTokenRef.current)
      .then((session) => {
        if (active) setKickoffStatus({ key: selectionKey, session });
      })
      .catch(() => {
        if (active) setKickoffStatus({ key: selectionKey, unavailable: true });
      });
    return () => {
      active = false;
    };
  }, [organizationId, assessmentId, selectionKey]);

  function markSessionClosed(sessionId) {
    setKickoffStatus((current) =>
      current?.key === selectionKey && current.session?.id === sessionId
        ? { ...current, session: { ...current.session, closed: true } }
        : current
    );
  }

  function changeOrganization(event) {
    const value = event.target.value;
    setError("");
    setOrganizationId(value);
    setAssessmentId("");
  }

  function changeAssessment(event) {
    setError("");
    setAssessmentId(event.target.value);
  }

  async function startInterview() {
    if (!canOpen) {
      return;
    }
    const seq = startSeqRef.current + 1;
    startSeqRef.current = seq;
    setIsStarting(true);
    setError("");
    try {
      const data = selectedSession.session?.closed
        ? await getInterview(organizationId, assessmentId, selectedSession.session.id, accessTokenRef.current)
        : await openInterview(organizationId, assessmentId, accessTokenRef.current);
      if (seq !== startSeqRef.current) {
        return;
      }
      if (!data?.session) {
        setError("The interview could not be started. Try again.");
        return;
      }
      setKickoffStatus({ key: selectionKey, session: data.session });
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

  const session = selectedSession?.session;
  let interviewStatus;
  if (selectedSession && !selectedSession.unavailable) {
    interviewStatus = session?.ended_at
      ? "Completed"
      : session?.closed
        ? "Closed"
        : session
          ? "In progress"
          : "Not started";
  }

  let openLabel = "Start interview";
  if (isStarting) {
    openLabel = "Opening…";
  } else if (selectedAssessment && !selectedSession) {
    openLabel = "Checking interview…";
  } else if (selectedSession?.session?.closed) {
    openLabel = "View interview";
  } else if (selectedSession?.session) {
    openLabel = "Resume interview";
  } else if (selectedSession?.unavailable) {
    openLabel = "Open interview";
  }

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
              <option key={item.id} value={item.id}>{item.title} · {assessmentStatusLabel(item.status)}</option>
            ))}
          </select>
        </label>
        <button className="primary-button" type="button" onClick={startInterview} disabled={!canOpen}>
          {openLabel}
        </button>
      </div>

      {selectedAssessment && interviewStatus && (
        <p className="interview-hint">Interview status: {interviewStatus}</p>
      )}

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
          onSessionClosed={markSessionClosed}
          accessToken={accessToken}
        />
      )}
    </section>
  );
}
