import { useEffect, useState } from "react";

import { checkApiHealth } from "./api/client.js";
import { useAuth } from "./auth/AuthProvider.jsx";
import InvitationActivation from "./auth/InvitationActivation.jsx";
import EvidencePage from "./features/organizations/EvidencePage.jsx";
import OrganizationWorkspace from "./features/organizations/OrganizationWorkspace.jsx";
import { getOrganization } from "./features/organizations/api.js";
import ExpertReviewWorkspace from "./features/expertReviews/ExpertReviewWorkspace.jsx";
import InterviewWorkspace from "./features/interviews/InterviewWorkspace.jsx";
import ReportWorkspace from "./features/reports/ReportWorkspace.jsx";
import AssessmentWorkspace from "./features/assessments/AssessmentWorkspace.jsx";

const EVIDENCE_PATH = "/evidence";
const organizationRoleLabels = {
  administrator: "Administrator",
  consultant: "Consultant",
  representative: "Representative",
};

function AccountChip({ user, organizationId }) {
  const [organization, setOrganization] = useState(null);
  const { accessToken, is_platform_admin: isPlatformAdmin } = user;

  useEffect(() => {
    if (!accessToken || !organizationId || isPlatformAdmin) return undefined;

    let active = true;
    getOrganization(organizationId, accessToken)
      .then((result) => {
        if (active) setOrganization(result);
      })
      .catch(() => {
        if (active) setOrganization(null);
      });
    return () => {
      active = false;
    };
  }, [accessToken, organizationId, isPlatformAdmin]);

  const role = isPlatformAdmin
    ? "Platform administrator"
    : organizationRoleLabels[organization?.role];

  return (
    <div className="account-chip" title={user.email}>
      <span className="account-email">{user.email}</span>
      {role && <span className="account-role" title={organization?.name}>{role}</span>}
    </div>
  );
}

function ApiStatus({ status, onRetry }) {
  const labels = {
    checking: "Checking API",
    online: "API connected",
    offline: "API unavailable",
  };
  return (
    <button
      className={`api-status status-${status}`}
      type="button"
      onClick={status === "offline" ? onRetry : undefined}
      disabled={status !== "offline"}
      aria-live="polite"
    >
      <span className="status-indicator" />
      {labels[status]}
    </button>
  );
}

function LoginPanel({ authError, onSignIn, isSupabaseConfigured, apiStatus, onRetryApi }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setShowPassword(false);
    setIsSubmitting(true);
    try {
      await onSignIn(email, password);
    } catch {
      setPassword("");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="login-panel">
      <div className="login-art" aria-hidden="true">
        <div className="orbit orbit-one" />
        <div className="orbit orbit-two" />
        <div className="login-core">AG</div>
        <span className="orbit-dot dot-one" />
        <span className="orbit-dot dot-two" />
      </div>
      <p className="eyebrow">SECURE CLIENT WORKSPACES</p>
      <h1>Welcome back<br />to <span>Agentic GRC.</span></h1>
      <p className="login-description">Sign in with the email address linked to your platform account.</p>
      {authError && <p className="inline-error" role="alert">{authError}</p>}
      <form className="login-form" onSubmit={submit}>
        <label>
          Email address
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            maxLength={320}
            required
            disabled={!isSupabaseConfigured}
          />
        </label>
        <div className="login-password-field">
          <label htmlFor="login-password">Password</label>
          <div className="login-password-control">
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              maxLength={128}
              required
              disabled={!isSupabaseConfigured}
            />
            <button
              className="login-password-toggle"
              type="button"
              aria-controls="login-password"
              aria-label={showPassword ? "Hide password" : "Show password"}
              onClick={() => setShowPassword((current) => !current)}
              disabled={!isSupabaseConfigured || isSubmitting}
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                focusable="false"
              >
                {showPassword ? (
                  <>
                    <path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8" />
                    <path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3 3.7M6.2 6.2C3.6 8.3 2 12 2 12s4 7 10 7a9.9 9.9 0 0 0 5.1-1.7" />
                  </>
                ) : (
                  <>
                    <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z" />
                    <circle cx="12" cy="12" r="3" />
                  </>
                )}
              </svg>
            </button>
          </div>
        </div>
        <button className="primary-button sign-in-button" type="submit" disabled={isSubmitting || !isSupabaseConfigured}>
          {isSubmitting ? "Signing in…" : "Sign in"}
          {!isSubmitting && <span aria-hidden="true">→</span>}
        </button>
      </form>
      <div className="login-divider"><span>OR</span></div>
      <button
        className="secondary-button google-sign-in-button"
        type="button"
        disabled
        aria-label="Continue with Google, pending configuration"
      >
        <span className="google-mark" aria-hidden="true">G</span>
        <span>Continue with Google</span>
        <span className="google-pending-tag">Pending</span>
      </button>
      <p className="login-help">New here? Ask your organization administrator for an invitation.</p>
      <div className="login-api-state">
        <ApiStatus status={apiStatus} onRetry={onRetryApi} />
        {apiStatus === "online" && <span>Backend health check passed</span>}
        {apiStatus === "offline" && <span>Start FastAPI, then retry</span>}
      </div>
    </section>
  );
}

function App() {
  const {
    user,
    isLoading,
    authError,
    signIn,
    signOut,
    isSupabaseConfigured,
  } = useAuth();
  const [apiStatus, setApiStatus] = useState("checking");
  const [currentView, setCurrentView] = useState("organizations");
  const [pathname, setPathname] = useState(window.location.pathname);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [reviewOrganizationId, setReviewOrganizationId] = useState("");
  const [interviewAssessmentId, setInterviewAssessmentId] = useState("");
  const isEvidencePage = pathname === EVIDENCE_PATH;
  const isExpertReview = !isEvidencePage && currentView === "expert-reviews";
  const headerOrganizationId = isExpertReview ? reviewOrganizationId : selectedOrganizationId;
  const evidencePath = selectedOrganizationId
    ? `${EVIDENCE_PATH}?organization_id=${encodeURIComponent(selectedOrganizationId)}`
    : EVIDENCE_PATH;

  useEffect(() => {
    const syncPath = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", syncPath);
    return () => window.removeEventListener("popstate", syncPath);
  }, []);

  useEffect(() => {
    if (!isExpertReview) setReviewOrganizationId("");
  }, [isExpertReview]);

  function navigate(path) {
    window.history.pushState({}, "", path);
    setPathname(window.location.pathname);
  }

  function navLink(path) {
    return (event) => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
        return;
      }
      event.preventDefault();
      navigate(path);
    };
  }

  function showView(view) {
    setCurrentView(view);
    if (isEvidencePage) {
      navigate("/");
    }
  }

  async function refreshApiStatus() {
    setApiStatus("checking");
    try {
      await checkApiHealth();
      setApiStatus("online");
    } catch {
      setApiStatus("offline");
    }
  }

  useEffect(() => {
    void refreshApiStatus();
  }, []);

  useEffect(() => {
    if (window.location.pathname === "/auth/callback" && !isLoading && user) {
      window.history.replaceState({}, document.title, "/");
    }
  }, [isLoading, user]);

  function openInterview(organizationId, assessmentId) {
    setSelectedOrganizationId(organizationId);
    setInterviewAssessmentId(assessmentId);
    showView("interview");
  }

  function handleSignOut() {
    setSelectedOrganizationId("");
    setReviewOrganizationId("");
    setInterviewAssessmentId("");
    signOut();
  }

  if (window.location.pathname === "/invite/accept") {
    return <InvitationActivation />;
  }

  if (window.location.pathname === "/auth/callback" && isLoading) {
    return <div className="loading-screen" role="status"><span className="loading-orb" />Completing secure sign-in…</div>;
  }

  return (
    <main className="app-shell">
      <aside className="app-rail">
        <a className="brand-lockup" href="/" aria-label="Agentic GRC home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span className="brand-name">AGENTIC<span>GRC</span><small>RISK INTELLIGENCE</small></span>
        </a>

        <div className="rail-divider" />
        <p className="rail-label">WORKSPACE</p>
        <button
          className={`rail-navigation-item ${!isEvidencePage && currentView === "organizations" ? "is-active" : ""}`}
          type="button"
          onClick={() => showView("organizations")}
          disabled={!user?.accessToken}
          aria-label="Client onboarding"
          aria-current={!isEvidencePage && currentView === "organizations" ? "page" : undefined}
        >
          <span className="rail-current-icon" aria-hidden="true">⌂</span>
          <span>Client onboarding</span>
          {!isEvidencePage && currentView === "organizations" && <span className="rail-active-dot" />}
        </button>

        <button
          className={`rail-navigation-item ${!isEvidencePage && currentView === "assessments" ? "is-active" : ""}`}
          type="button"
          onClick={() => showView("assessments")}
          disabled={!user?.accessToken}
          aria-label="Assessments"
          aria-current={!isEvidencePage && currentView === "assessments" ? "page" : undefined}
        >
          <span className="rail-current-icon" aria-hidden="true">◇</span>
          <span>Assessments</span>
          {!isEvidencePage && currentView === "assessments" && <span className="rail-active-dot" />}
        </button>

        <button
          className={`rail-navigation-item ${!isEvidencePage && currentView === "interview" ? "is-active" : ""}`}
          type="button"
          onClick={() => showView("interview")}
          disabled={!user?.accessToken}
          aria-label="Interview"
          aria-current={!isEvidencePage && currentView === "interview" ? "page" : undefined}
        >
          <span className="rail-current-icon" aria-hidden="true">✎</span>
          <span>Interview</span>
          {!isEvidencePage && currentView === "interview" && <span className="rail-active-dot" />}
        </button>

        <button
          className={`rail-navigation-item ${!isEvidencePage && currentView === "expert-reviews" ? "is-active" : ""}`}
          type="button"
          onClick={() => showView("expert-reviews")}
          disabled={!user?.accessToken}
          aria-label="Expert reviews"
          aria-current={!isEvidencePage && currentView === "expert-reviews" ? "page" : undefined}
        >
          <span className="rail-current-icon" aria-hidden="true">✓</span>
          <span>Expert reviews</span>
          {!isEvidencePage && currentView === "expert-reviews" && <span className="rail-active-dot" />}
        </button>

        <button
          className={`rail-navigation-item ${!isEvidencePage && currentView === "reports" ? "is-active" : ""}`}
          type="button"
          onClick={() => showView("reports")}
          disabled={!user?.accessToken}
          aria-label="Reports"
          aria-current={!isEvidencePage && currentView === "reports" ? "page" : undefined}
        >
          <span className="rail-current-icon" aria-hidden="true">▤</span>
          <span>Reports</span>
          {!isEvidencePage && currentView === "reports" && <span className="rail-active-dot" />}
        </button>

        {user?.accessToken && (
          <a
            className={`rail-navigation-item ${isEvidencePage ? "is-active" : ""}`}
            href={evidencePath}
            onClick={navLink(evidencePath)}
            aria-label="Evidence upload"
            aria-current={isEvidencePage ? "page" : undefined}
          >
            <span className="rail-current-icon" aria-hidden="true">⇪</span>
            <span>Evidence upload</span>
            {isEvidencePage && <span className="rail-active-dot" />}
          </a>
        )}

        <div className="rail-bottom">
          <div className="rail-help-mark" aria-hidden="true">?</div>
          <div><strong>Need a hand?</strong><span>Ask your administrator</span></div>
        </div>
      </aside>

      <section className="app-main">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Platform</span>
            <span aria-hidden="true">/</span>
            <strong>
              {isEvidencePage
                ? "Evidence upload"
                : currentView === "assessments"
                  ? "Assessments"
                  : currentView === "interview"
                    ? "Interview"
                    : currentView === "reports"
                      ? "Reports"
                      : currentView === "expert-reviews"
                        ? "Expert reviews"
                        : "Organization setup"}
            </strong>
          </div>
          <div className="topbar-actions">
            <ApiStatus status={apiStatus} onRetry={refreshApiStatus} />
            {user && (
              <>
                <AccountChip
                  key={JSON.stringify([user.id, headerOrganizationId])}
                  user={user}
                  organizationId={headerOrganizationId}
                />
                <button className="sign-out-button" type="button" onClick={handleSignOut}>Sign out</button>
              </>
            )}
          </div>
        </header>

        {isLoading ? (
          <div className="loading-screen" role="status"><span className="loading-orb" />Loading secure workspace…</div>
        ) : user?.accessToken && isEvidencePage ? (
          <EvidencePage
            accessToken={user.accessToken}
            sessionId={user.id}
            onNavigate={navigate}
            onOrganizationChange={setSelectedOrganizationId}
          />
        ) : user?.accessToken ? (
          currentView === "assessments" ? (
            <AssessmentWorkspace
              key={user.id}
              accessToken={user.accessToken}
              sessionId={user.id}
              isPlatformAdmin={user.is_platform_admin}
              initialOrganizationId={selectedOrganizationId}
              onOrganizationChange={setSelectedOrganizationId}
              onStartInterview={openInterview}
            />
          ) : currentView === "reports" ? (
            <ReportWorkspace
              accessToken={user.accessToken}
              sessionId={user.id}
              initialOrganizationId={selectedOrganizationId}
              onOrganizationChange={setSelectedOrganizationId}
            />
          ) : currentView === "interview" ? (
            <InterviewWorkspace
              key={`${user.id}:${interviewAssessmentId}`}
              accessToken={user.accessToken}
              sessionId={user.id}
              initialOrganizationId={selectedOrganizationId}
              initialAssessmentId={interviewAssessmentId}
              onOrganizationChange={setSelectedOrganizationId}
            />
          ) : currentView === "expert-reviews" ? (
            <ExpertReviewWorkspace
              key={user.id}
              accessToken={user.accessToken}
              sessionId={user.id}
              onOrganizationChange={setReviewOrganizationId}
            />
          ) : (
            <>
              <a className="primary-button evidence-home-link" href={evidencePath} onClick={navLink(evidencePath)}>
                Upload evidence <span aria-hidden="true">→</span>
              </a>
              <OrganizationWorkspace
                accessToken={user.accessToken}
                isPlatformAdmin={user.is_platform_admin}
                initialOrganizationId={selectedOrganizationId}
                onOrganizationChange={setSelectedOrganizationId}
              />
            </>
          )
        ) : (
          <LoginPanel
            authError={authError}
            onSignIn={signIn}
            isSupabaseConfigured={isSupabaseConfigured}
            apiStatus={apiStatus}
            onRetryApi={refreshApiStatus}
          />
        )}
      </section>
    </main>
  );
}

export default App;
