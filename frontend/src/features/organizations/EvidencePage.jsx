import { useEffect, useState } from "react";

import EvidenceUpload from "./EvidenceUpload.jsx";
import { listOrganizations } from "./api.js";

function readOrganizationParam() {
  return new URLSearchParams(window.location.search).get("organization_id") || "";
}

export default function EvidencePage({ accessToken, onNavigate }) {
  const [organizations, setOrganizations] = useState([]);
  const [selectedId, setSelectedId] = useState(readOrganizationParam);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let isActive = true;

    async function load() {
      try {
        const items = await listOrganizations(accessToken);
        if (!isActive) {
          return;
        }
        setOrganizations(items);
        setSelectedId((current) => (
          items.some((organization) => organization.id === current) ? current : items[0]?.id || ""
        ));
      } catch (loadError) {
        if (isActive) {
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
  }, [accessToken]);

  function selectOrganization(event) {
    const id = event.target.value;
    setSelectedId(id);
    const url = new URL(window.location.href);
    url.searchParams.set("organization_id", id);
    window.history.replaceState({}, "", url);
  }

  if (isLoading) {
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

      {error && <p className="inline-error" role="alert">{error}</p>}

      {!error && organizations.length === 0 && (
        <p className="muted-copy">You are not an active member of any organization yet.</p>
      )}

      {organizations.length > 0 && (
        <>
          <label className="evidence-organization-select">
            Organization
            <select value={selectedId} onChange={selectOrganization}>
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>{organization.name}</option>
              ))}
            </select>
          </label>
          <EvidenceUpload organizationId={selectedId} accessToken={accessToken} />
        </>
      )}
    </div>
  );
}
