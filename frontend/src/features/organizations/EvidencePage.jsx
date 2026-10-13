import { useEffect, useRef, useState } from "react";

import EvidenceUpload from "./EvidenceUpload.jsx";
import { listOrganizations } from "./api.js";

function readOrganizationParam() {
  return new URLSearchParams(window.location.search).get("organization_id") || "";
}

export default function EvidencePage({ accessToken, sessionId = "", onNavigate, onOrganizationChange }) {
  const [loaded, setLoaded] = useState(null);
  const [loadedOrganizations, setLoadedOrganizations] = useState([]);
  const [loadedSelectedId, setLoadedSelectedId] = useState("");
  const [loadedError, setLoadedError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [reloadCount, setReloadCount] = useState(0);
  const tokenRef = useRef(accessToken);

  const isCurrent = loaded?.id === sessionId;
  const organizations = isCurrent ? loadedOrganizations : [];
  const selectedId = isCurrent ? loadedSelectedId : "";
  const error = isCurrent ? loadedError : "";
  const selectedOrganization = organizations.find((organization) => organization.id === selectedId);

  useEffect(() => {
    tokenRef.current = accessToken;
  }, [accessToken]);

  useEffect(() => {
    if (isCurrent && loadedError) {
      setReloadCount((current) => current + 1);
    }
  }, [accessToken]);

  useEffect(() => {
    if (isCurrent && !isLoading && !error) {
      onOrganizationChange?.(selectedOrganization?.id || "");
    }
  }, [isCurrent, isLoading, error, onOrganizationChange, selectedOrganization]);

  useEffect(() => {
    let isActive = true;

    async function load() {
      setIsLoading(true);
      setLoadedError("");
      try {
        const items = await listOrganizations(tokenRef.current, { activeMembershipsOnly: true });
        if (!isActive) {
          return;
        }
        const requested = readOrganizationParam();
        setLoadedOrganizations(items);
        setLoadedSelectedId(items.some((organization) => organization.id === requested) ? requested : "");
        setLoaded({ id: sessionId });
      } catch (loadError) {
        if (isActive) {
          setLoadedOrganizations([]);
          setLoadedSelectedId("");
          setLoadedError(loadError?.status === 401
            ? "Your session has expired. Sign in again to continue."
            : loadError?.message || "Could not load your organizations.");
          setLoaded({ id: sessionId });
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void load();
    return () => {
      isActive = false;
    };
  }, [sessionId, reloadCount]);

  function selectOrganization(event) {
    const id = event.target.value;
    setLoadedSelectedId(id);
    const url = new URL(window.location.href);
    url.searchParams.set("organization_id", id);
    window.history.replaceState({}, "", url);
  }

  if (!isCurrent || (isLoading && organizations.length === 0)) {
    return <div className="loading-panel" role="status">Loading your organizations…</div>;
  }

  return (
    <div className="evidence-page">
      <a
        className="text-button"
        href="/"
        onClick={(event) => {
          event.preventDefault();
          onNavigate("/");
        }}
      >
        ← Back to workspaces
      </a>

      <div className="evidence-page-heading">
        <p className="eyebrow">EVIDENCE</p>
        <h1>Evidence upload</h1>
        <p className="muted-copy">Upload documents for an organization. Text is extracted automatically.</p>
      </div>

      <p className="muted-copy">Only organizations where you have an active membership are available for upload.</p>

      {error && (
        <div>
          <p className="inline-error" role="alert">{error}</p>
          <button className="secondary-button" type="button" onClick={() => setReloadCount((current) => current + 1)}>
            Retry loading organizations
          </button>
        </div>
      )}

      {!error && organizations.length === 0 && (
        <p className="muted-copy">You are not an active member of any organization yet.</p>
      )}

      {organizations.length > 0 && (
        <>
          <label className="evidence-organization-select">
            Organization
            <select value={selectedOrganization?.id || ""} onChange={selectOrganization} disabled={isLoading}>
              <option value="">Select an organization</option>
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>{organization.name}</option>
              ))}
            </select>
          </label>
          <p className="evidence-target" aria-live="polite">
            Upload to: <strong>{selectedOrganization?.name || "Select an organization before uploading"}</strong>
          </p>
          <EvidenceUpload
            key={selectedOrganization?.id || "unselected"}
            organizationId={selectedOrganization?.id || ""}
            accessToken={accessToken}
            sessionId={sessionId}
            disabled={isLoading || !!error || !selectedOrganization}
          />
        </>
      )}
    </div>
  );
}
