import { useEffect, useState } from "react";

import { checkApiHealth } from "./api/client.js";
import { useAuth } from "./auth/AuthProvider.jsx";
import InvitationActivation from "./auth/InvitationActivation.jsx";
import EvidencePage from "./features/organizations/EvidencePage.jsx";
import OrganizationWorkspace from "./features/organizations/OrganizationWorkspace.jsx";
import ExpertReviewWorkspace from "./features/expertReviews/ExpertReviewWorkspace.jsx";
import ReportWorkspace from "./features/reports/ReportWorkspace.jsx";

const EVIDENCE_PATH = "/evidence";

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
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();
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
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            maxLength={128}
            required
            disabled={!isSupabaseConfigured}
          />
        </label>
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
  const isEvidencePage = pathname === EVIDENCE_PATH;
  const evidencePath = selectedOrganizationId
    ? `${EVIDENCE_PATH}?organization_id=${encodeURIComponent(selectedOrganizationId)}`
    : EVIDENCE_PATH;

  useEffect(() => {
    const syncPath = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", syncPath);
    return () => window.removeEventListener("popstate", syncPath);
  }, []);

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

  function handleSignOut() {
    setSelectedOrganizationId("");
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
                <div className="account-chip" title={user.email}>
                  <span className="account-avatar" aria-hidden="true">{(user.email || "U").slice(0, 1).toUpperCase()}</span>
                  <span className="account-email">{user.email}</span>
                </div>
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
          currentView === "reports" ? (
            <ReportWorkspace
              accessToken={user.accessToken}
              sessionId={user.id}
              initialOrganizationId={selectedOrganizationId}
              onOrganizationChange={setSelectedOrganizationId}
            />
          ) : currentView === "expert-reviews" ? (
            <ExpertReviewWorkspace
              accessToken={user.accessToken}
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
