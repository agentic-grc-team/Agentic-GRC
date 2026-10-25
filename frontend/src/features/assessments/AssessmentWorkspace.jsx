import { useEffect, useRef, useState } from "react";

import { listOrganizations } from "../organizations/api.js";
import { createAssessment, getAssessmentScope, listAssessments } from "./api.js";
import AssessmentScope from "./AssessmentScope.jsx";
import { assessmentStatusLabel } from "./statusLabels.js";
import "./AssessmentWorkspace.css";

// The backend lets administrators and consultants start an assessment (HU-04); every member can see its scope.
const CREATOR_ROLES = ["administrator", "consultant"];

function describeError(error) {
  if (error?.status === 401) {
    return "Your session has expired. Sign in again to continue.";
  }
  if (error?.status === 404) {
    return "This assessment was not found, or you do not have access to it.";
  }
  const detail = error?.body?.detail;
  if (error?.status === 422 && Array.isArray(detail) && detail[0]?.msg) {
    return detail[0].msg.replace(/^Value error, /, "");
  }
  return error?.message || "Something went wrong. Please try again.";
}

// Create an assessment and see what it covers before the interview starts (HU-04, AGRC-62).
export default function AssessmentWorkspace({
  accessToken,
  sessionId,
  isPlatformAdmin = false,
  initialOrganizationId = "",
  onOrganizationChange,
}) {
  const [organizations, setOrganizations] = useState([]);
  const [isLoadingOrganizations, setIsLoadingOrganizations] = useState(true);
  const [organizationsError, setOrganizationsError] = useState("");
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");

  const [assessments, setAssessments] = useState([]);
  const [isLoadingAssessments, setIsLoadingAssessments] = useState(false);
  const [assessmentsError, setAssessmentsError] = useState("");
  const [selectedAssessmentId, setSelectedAssessmentId] = useState("");
  const [assessmentsReload, setAssessmentsReload] = useState(0);

  const [scope, setScope] = useState(null);
  const [isLoadingScope, setIsLoadingScope] = useState(false);
  const [scopeError, setScopeError] = useState("");

  const [title, setTitle] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [notice, setNotice] = useState("");

  // Requests always use the latest token, so a token refresh does not reload the screen.
  const accessTokenRef = useRef(accessToken);
  const initialOrganizationIdRef = useRef(initialOrganizationId);
  const onOrganizationChangeRef = useRef(onOrganizationChange);
  const createdAssessmentIdRef = useRef("");
  // A create that finishes after the user switched organization must not change the new organization's screen.
  const selectedOrganizationIdRef = useRef("");
  const sessionKey = sessionId ?? accessToken;

  useEffect(() => {
    accessTokenRef.current = accessToken;
  }, [accessToken]);

  useEffect(() => {
    onOrganizationChangeRef.current = onOrganizationChange;
  }, [onOrganizationChange]);

  useEffect(() => {
    selectedOrganizationIdRef.current = selectedOrganizationId;
    if (selectedOrganizationId) {
      onOrganizationChangeRef.current?.(selectedOrganizationId);
    }
  }, [selectedOrganizationId]);

  useEffect(() => {
    let active = true;
    setIsLoadingOrganizations(true);
    setOrganizationsError("");

    listOrganizations(accessTokenRef.current)
      .then((items) => {
        if (!active) return;
        const list = Array.isArray(items) ? items : [];
        setOrganizations(list);
        const preferred = list.find((item) => item.id === initialOrganizationIdRef.current);
        setSelectedOrganizationId(preferred ? preferred.id : list[0]?.id || "");
      })
      .catch((error) => {
        if (!active) return;
        setOrganizations([]);
        setSelectedOrganizationId("");
        setOrganizationsError(describeError(error));
      })
      .finally(() => {
        if (active) setIsLoadingOrganizations(false);
      });

    return () => {
      active = false;
    };
  }, [sessionKey]);

  useEffect(() => {
    let active = true;
    setAssessments([]);
    setAssessmentsError("");
    setSelectedAssessmentId("");
    if (!selectedOrganizationId) {
      setIsLoadingAssessments(false);
      return undefined;
    }
    setIsLoadingAssessments(true);

    listAssessments(selectedOrganizationId, accessTokenRef.current)
      .then((items) => {
        if (!active) return;
        const list = Array.isArray(items) ? items : [];
        setAssessments(list);
        const created = list.find((item) => item.id === createdAssessmentIdRef.current);
        createdAssessmentIdRef.current = "";
        setSelectedAssessmentId(created ? created.id : list[0]?.id || "");
      })
      .catch((error) => {
        if (!active) return;
        setAssessmentsError(describeError(error));
      })
      .finally(() => {
        if (active) setIsLoadingAssessments(false);
      });

    return () => {
      active = false;
    };
  }, [selectedOrganizationId, sessionKey, assessmentsReload]);

  useEffect(() => {
    let active = true;
    setScope(null);
    setScopeError("");
    if (!selectedOrganizationId || !selectedAssessmentId) {
      setIsLoadingScope(false);
      return undefined;
    }
    setIsLoadingScope(true);

    getAssessmentScope(selectedOrganizationId, selectedAssessmentId, accessTokenRef.current)
      .then((data) => {
        if (active) setScope(data);
      })
      .catch((error) => {
        if (active) setScopeError(describeError(error));
      })
      .finally(() => {
        if (active) setIsLoadingScope(false);
      });

    return () => {
      active = false;
    };
  }, [selectedOrganizationId, selectedAssessmentId, sessionKey]);

  const selectedOrganization = organizations.find((item) => item.id === selectedOrganizationId) || null;
  const canCreate = Boolean(
    selectedOrganization && (isPlatformAdmin || CREATOR_ROLES.includes(selectedOrganization.role)),
  );

  function selectOrganization(organizationId) {
    selectedOrganizationIdRef.current = organizationId;
    setSelectedOrganizationId(organizationId);
    setNotice("");
    setCreateError("");
  }

  function selectAssessment(assessmentId) {
    setSelectedAssessmentId(assessmentId);
    // The "was created" notice only describes the assessment that was just created.
    setNotice("");
  }

  async function submitAssessment(event) {
    event.preventDefault();
    const trimmedTitle = title.trim();
    if (!trimmedTitle || !selectedOrganizationId || isCreating) {
      return;
    }
    const organizationId = selectedOrganizationId;
    setIsCreating(true);
    setCreateError("");
    setNotice("");
    try {
      const created = await createAssessment(organizationId, trimmedTitle, accessTokenRef.current);
      if (selectedOrganizationIdRef.current !== organizationId) return;
      setTitle("");
      setNotice(`"${created.title}" was created. Its scope is shown below.`);
      createdAssessmentIdRef.current = created.id;
      setAssessmentsReload((count) => count + 1);
    } catch (error) {
      if (selectedOrganizationIdRef.current !== organizationId) return;
      setCreateError(describeError(error));
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <section className="assessment-workspace" aria-labelledby="assessment-workspace-heading">
      <p className="eyebrow">SECURITY ASSESSMENTS</p>
      <h1 id="assessment-workspace-heading">Assessments</h1>
      <p className="assessment-intro">
        Start an assessment for an organization and check which NIST CSF 2.0 functions, categories and
        controls it covers before the interview begins.
      </p>

      {isLoadingOrganizations && <p role="status">Loading organizations…</p>}
      {organizationsError && <p role="alert">{organizationsError}</p>}
      {!isLoadingOrganizations && !organizationsError && organizations.length === 0 && (
        <p className="assessment-empty">
          You are not a member of any organization yet. Ask your administrator for an invitation.
        </p>
      )}

      {organizations.length > 0 && (
        <label className="assessment-field">
          Organization
          <select value={selectedOrganizationId} onChange={(event) => selectOrganization(event.target.value)}>
            {organizations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {canCreate && (
        <form className="assessment-create-form" onSubmit={submitAssessment}>
          <label className="assessment-field">
            New assessment title
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={255}
              placeholder="e.g. Q4 identity and access review"
              required
            />
          </label>
          <button className="primary-button" type="submit" disabled={isCreating || !title.trim()}>
            {isCreating ? "Creating…" : "Create assessment"}
          </button>
        </form>
      )}
      {selectedOrganization && !canCreate && (
        <p className="assessment-note">
          An administrator or consultant creates assessments. You can see the scope of the existing ones below.
        </p>
      )}
      {createError && <p role="alert">{createError}</p>}
      {notice && <p role="status">{notice}</p>}

      {isLoadingAssessments && <p role="status">Loading assessments…</p>}
      {assessmentsError && <p role="alert">{assessmentsError}</p>}
      {selectedOrganization && !isLoadingAssessments && !assessmentsError && assessments.length === 0 && (
        <p className="assessment-empty">This organization has no assessments yet.</p>
      )}

      {assessments.length > 0 && (
        <label className="assessment-field">
          Assessment
          <select value={selectedAssessmentId} onChange={(event) => selectAssessment(event.target.value)}>
            {assessments.map((item) => (
              <option key={item.id} value={item.id}>
                {`${item.title} · ${assessmentStatusLabel(item.status)}`}
              </option>
            ))}
          </select>
        </label>
      )}

      {isLoadingScope && <p role="status">Loading assessment scope…</p>}
      {scopeError && <p role="alert">{scopeError}</p>}
      {scope && <AssessmentScope scope={scope} />}
    </section>
  );
}
