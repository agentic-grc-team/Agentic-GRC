import { useEffect, useState } from "react";

import EvidenceUpload from "./EvidenceUpload.jsx";
import { listOrganizations } from "./api.js";

function readOrganizationParam() {
  return new URLSearchParams(window.location.search).get("organization_id") || "";
}

export default function EvidencePage({ accessToken, onNavigate, onOrganizationChange }) {
  const [organizations, setOrganizations] = useState([]);
  const [selectedId, setSelectedId] = useState(readOrganizationParam);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadCount, setReloadCount] = useState(0);
  const selectedOrganization = organizations.find((organization) => organization.id === selectedId);

  useEffect(() => {
    if (!isLoading && !error) {
      onOrganizationChange?.(selectedOrganization?.id || "");
    }
  }, [isLoading, error, onOrganizationChange, selectedOrganization]);

  useEffect(() => {
    let isActive = true;

    async function load() {
      setIsLoading(true);
      setError("");
      try {
        const items = await listOrganizations(accessToken, { activeMembershipsOnly: true });
        if (!isActive) {
          return;
        }
        setOrganizations(items);
        setSelectedId((current) => (
          items.some((organization) => organization.id === current) ? current : ""
        ));
      } catch (loadError) {
        if (isActive) {
          setOrganizations([]);
          setSelectedId("");
          setError(loadError?.status === 401
            ? "Your session has expired. Sign in again to continue."
            : loadError?.message || "Could not load your organizations.");
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
  }, [accessToken, reloadCount]);

  function selectOrganization(event) {
    const id = event.target.value;
    setSelectedId(id);
    const url = new URL(window.location.href);
    url.searchParams.set("organization_id", id);
    window.history.replaceState({}, "", url);
  }

  if (isLoading && organizations.length === 0) {
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
            disabled={isLoading || !!error || !selectedOrganization}
          />
        </>
      )}
    </div>
  );
}
