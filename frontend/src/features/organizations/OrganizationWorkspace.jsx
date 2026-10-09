import { useCallback, useEffect, useMemo, useState } from "react";

import {
  acceptInvitation,
  createInvitation,
  createOrganization,
  listIndustrySectors,
  listMyInvitations,
  listOrganizations,
  listOrganizationSizes,
} from "./api.js";

const initialOrganization = { name: "", sector_code: "", size_code: "" };

function describeApiError(error) {
  if (error?.status === 401) {
    return "Your session has expired. Sign in again to continue.";
  }
  if (error?.status === 403) {
    return "You do not have administrator access for this organization.";
  }
  if (error?.status === 503) {
    return "Authentication or email delivery is not configured. Check the backend settings and try again.";
  }
  return error?.message || "Something went wrong. Please try again.";
}

function AssistantMessage({ children, timestamp = "NOW" }) {
  return (
    <div className="message-row assistant-message">
      <div className="assistant-avatar" aria-hidden="true">A</div>
      <div className="message-content">
        <div className="message-meta"><strong>GRC ASSISTANT</strong><span>{timestamp}</span></div>
        <div className="message-bubble">{children}</div>
      </div>
    </div>
  );
}

function OrganizationForm({ onCreate, isSubmitting, duplicateMatches, onConfirmDuplicate, onDismissDuplicates, sectors, sizes }) {
  const [form, setForm] = useState(initialOrganization);

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function submit(event, confirmDuplicateOf = null) {
    event.preventDefault();
    const didCreate = await onCreate(form, confirmDuplicateOf);
    if (didCreate) {
      setForm(initialOrganization);
    }
  }

  return (
    <div className="form-card">
      <div className="form-card-heading">
        <span className="step-indicator">01</span>
        <div>
          <p className="eyebrow">CLIENT PROFILE</p>
          <h2>Set up an organization</h2>
          <p className="muted-copy">These details create a separate workspace and will be available as future assessment context.</p>
        </div>
      </div>

      <form onSubmit={(event) => submit(event)} className="organization-form">
        <label>
          <span>Organization name <span className="required-mark">*</span></span>
          <input
            name="name"
            value={form.name}
            onChange={updateField}
            maxLength={255}
            autoComplete="organization"
            placeholder="e.g. Northstar Health"
            required
          />
        </label>
        <div className="form-row">
          <label>
            <span>Sector <span className="required-mark">*</span></span>
            <select
              name="sector_code"
              value={form.sector_code}
              onChange={updateField}
              required
            >
              <option value="">Choose a sector</option>
              {sectors.map((sector) => <option key={sector.code} value={sector.code}>{sector.label}</option>)}
            </select>
          </label>
          <label>
            <span>Organization size <span className="required-mark">*</span></span>
            <select
              name="size_code"
              value={form.size_code}
              onChange={updateField}
              required
            >
              <option value="">Choose organization size</option>
              {sizes.map((size) => <option key={size.code} value={size.code}>{size.label}</option>)}
            </select>
          </label>
        </div>

        <div className="form-footer">
          <p><span className="privacy-dot" />Workspace data is separated by organization.</p>
          <button className="primary-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating workspace…" : "Create workspace"}
            {!isSubmitting && <span aria-hidden="true">→</span>}
          </button>
        </div>
      </form>

      {duplicateMatches.length > 0 && (
        <section className="duplicate-panel" aria-labelledby="duplicate-title" role="alert">
          <div className="duplicate-icon" aria-hidden="true">!</div>
          <div className="duplicate-copy">
            <p className="eyebrow">NAME ALREADY IN USE</p>
            <h3 id="duplicate-title">Confirm this is a separate client</h3>
            <p>Choose the existing organization this new workspace should be linked to. This will not merge their data.</p>
            <div className="duplicate-actions">
              {duplicateMatches.map((organization) => (
                <button
                  className="secondary-button"
                  key={organization.id}
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => onConfirmDuplicate(organization.id, form)}
                >
                  Confirm separate workspace for {organization.name}
                </button>
              ))}
              <button className="text-button" type="button" onClick={onDismissDuplicates}>
                Use a different name
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function OrganizationSelector({ organizations, selectedId, onSelect }) {
  return (
    <div className="organization-list" aria-label="Your organizations">
      {organizations.map((organization) => (
        <button
          type="button"
          className={`organization-list-item${organization.id === selectedId ? " is-selected" : ""}`}
          key={organization.id}
          onClick={() => onSelect(organization.id)}
          aria-current={organization.id === selectedId ? "true" : undefined}
        >
          <span className="organization-monogram" aria-hidden="true">
            {organization.name.trim().slice(0, 1).toUpperCase() || "O"}
          </span>
          <span className="organization-list-copy">
            <strong>{organization.name}</strong>
            <small>{organization.role}</small>
          </span>
          <span className="organization-chevron" aria-hidden="true">›</span>
        </button>
      ))}
      {organizations.length === 0 && <p className="sidebar-empty">No workspaces yet</p>}
    </div>
  );
}

function InvitationInbox({ invitations, onAccept, acceptingId }) {
  if (invitations.length === 0) {
    return null;
  }

  return (
    <section className="inbox-card" aria-labelledby="invitations-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">INVITATIONS</p>
          <h2 id="invitations-title">Waiting for your response</h2>
        </div>
        <span className="count-pill">{invitations.length}</span>
      </div>
      <ul className="invitation-list">
        {invitations.map((invitation) => (
          <li className="invitation-item" key={invitation.id}>
            <div className="invitation-details">
              <strong>{invitation.organization_name}</strong>
              <span>{invitation.role} access · expires {new Date(invitation.expires_at).toLocaleDateString()}</span>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => onAccept(invitation.id)}
              disabled={acceptingId === invitation.id}
            >
              {acceptingId === invitation.id ? "Joining…" : "Accept"}
            </button>
          </li>
        ))}
      </ul>
      <p className="delivery-note">Accepting creates your profile and grants access to the organization.</p>
    </section>
  );
}

export default function OrganizationWorkspace({ accessToken, isPlatformAdmin = false }) {
  const [organizations, setOrganizations] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [sizes, setSizes] = useState([]);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [duplicateMatches, setDuplicateMatches] = useState([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("consultant");
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [isInviting, setIsInviting] = useState(false);
  const [acceptingId, setAcceptingId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedOrganization = useMemo(
    () => organizations.find((organization) => organization.id === selectedOrganizationId) || null,
    [organizations, selectedOrganizationId],
  );
  const canCreateOrganization = isPlatformAdmin || organizations.some((organization) => organization.role === "administrator");

  const refreshWorkspace = useCallback(async (preferredOrganizationId = "") => {
    setError("");
    try {
      const [nextOrganizations, nextInvitations, nextSectors, nextSizes] = await Promise.all([
        listOrganizations(accessToken),
        listMyInvitations(accessToken),
        listIndustrySectors(accessToken),
        listOrganizationSizes(accessToken),
      ]);
      setOrganizations(nextOrganizations);
      setInvitations(nextInvitations);
      setSectors(nextSectors);
      setSizes(nextSizes);
      setSelectedOrganizationId((currentId) => {
        const preferredExists = nextOrganizations.some((item) => item.id === preferredOrganizationId);
        const currentExists = nextOrganizations.some((item) => item.id === currentId);
        return preferredExists ? preferredOrganizationId : currentExists ? currentId : nextOrganizations[0]?.id || "";
      });
    } catch (loadError) {
      setError(describeApiError(loadError));
    } finally {
      setIsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void refreshWorkspace();
  }, [refreshWorkspace]);

  async function submitOrganization(form, confirmDuplicateOf = null) {
    setError("");
    setNotice("");
    setIsCreating(true);
    setDuplicateMatches([]);
    const payload = {
      name: form.name.trim(),
      sector_code: form.sector_code,
      size_code: form.size_code,
    };
    if (confirmDuplicateOf) {
      payload.confirm_duplicate_of = confirmDuplicateOf;
    }

    try {
      const created = await createOrganization(payload, accessToken);
      await refreshWorkspace(created.id);
      setNotice(`${created.name} is ready. Its assessment workspace starts empty.`);
      return true;
    } catch (createError) {
      const detail = createError?.body?.detail;
      if (createError?.status === 409 && detail?.code === "duplicate_name_requires_confirmation") {
        setDuplicateMatches(detail.matches || []);
      } else {
        setError(describeApiError(createError));
      }
      return false;
    } finally {
      setIsCreating(false);
    }
  }

  async function confirmDuplicate(organizationId, form) {
    await submitOrganization(form, organizationId);
  }

  async function submitInvitation(event) {
    event.preventDefault();
    if (!selectedOrganization) {
      return;
    }
    setError("");
    setNotice("");
    setIsInviting(true);
    try {
      const invitation = await createInvitation(selectedOrganization.id, inviteEmail.trim(), inviteRole, accessToken);
      setInviteEmail("");
      setNotice(`An invitation email was sent to ${invitation.email}. The link expires in seven days.`);
    } catch (inviteError) {
      setError(describeApiError(inviteError));
    } finally {
      setIsInviting(false);
    }
  }

  async function acceptPendingInvitation(invitationId) {
    setError("");
    setNotice("");
    setAcceptingId(invitationId);
    try {
      await acceptInvitation(invitationId, accessToken);
      await refreshWorkspace();
      setNotice("You joined the organization. It is now available in your workspace list.");
    } catch (acceptError) {
      setError(describeApiError(acceptError));
    } finally {
      setAcceptingId("");
    }
  }

  if (isLoading) {
    return <div className="loading-panel" role="status">Loading your organization workspaces…</div>;
  }

  return (
    <div className="workspace-layout">
      <aside className="workspace-sidebar" aria-label="Organization navigation">
        <div className="sidebar-section-heading">
          <div>
            <p className="eyebrow">CLIENT WORKSPACES</p>
            <span className="sidebar-section-title">Organizations</span>
          </div>
          <span className="count-pill">{organizations.length}</span>
        </div>
        <OrganizationSelector
          organizations={organizations}
          selectedId={selectedOrganizationId}
          onSelect={(organizationId) => {
            setSelectedOrganizationId(organizationId);
            setNotice("");
            setError("");
          }}
        />
        <div className="sidebar-footnote">
          <span className="privacy-dot" />
          <span>Each organization has a separate logical data space.</span>
        </div>
      </aside>

      <section className="conversation-panel" aria-label="Organization setup conversation">
        <div className="conversation-heading">
          <div className="conversation-title-wrap">
            <span className="conversation-orb" aria-hidden="true"><span /></span>
            <div>
              <p className="eyebrow">WORKSPACE SETUP</p>
              <h1>{selectedOrganization ? selectedOrganization.name : "Start with a client"}</h1>
            </div>
          </div>
          <div className="secure-label"><span /> SECURE SESSION</div>
        </div>

        <div className="conversation-scroll">
          <div className="date-divider"><span>ORGANIZATION ONBOARDING</span></div>
          <AssistantMessage>
            <p>Let’s create a dedicated workspace for your client. I’ll need a few basic details to get started.</p>
            <div className="assistant-context-note">
              <span className="context-icon" aria-hidden="true">↳</span>
              <span>Sector and size are saved as organization context for future assessment interviews.</span>
            </div>
          </AssistantMessage>

          {error && <div className="alert alert-error" role="alert"><span aria-hidden="true">!</span>{error}</div>}
          {notice && <div className="alert alert-success" role="status"><span aria-hidden="true">✓</span>{notice}</div>}

          {canCreateOrganization ? (
            <OrganizationForm
              onCreate={submitOrganization}
              isSubmitting={isCreating}
              duplicateMatches={duplicateMatches}
              onConfirmDuplicate={confirmDuplicate}
              onDismissDuplicates={() => setDuplicateMatches([])}
              sectors={sectors}
              sizes={sizes}
            />
          ) : organizations.length === 0 ? (
            <div className="empty-state-card access-notice">
              <div className="empty-state-mark" aria-hidden="true">↗</div>
              <div>
                <h3>Your account is ready</h3>
                <p>An organization administrator can invite you to a client workspace.</p>
              </div>
            </div>
          ) : null}

          {selectedOrganization && (
            <>
              <div className="workspace-summary-card">
                <div className="summary-icon" aria-hidden="true">{selectedOrganization.name.slice(0, 1).toUpperCase()}</div>
                <div className="summary-main">
                  <p className="eyebrow">ACTIVE WORKSPACE</p>
                  <h2>{selectedOrganization.name}</h2>
                  <p>{selectedOrganization.sector} <span>·</span> {selectedOrganization.size}</p>
                </div>
                <span className="role-badge">{selectedOrganization.role}</span>
              </div>

              <div className="empty-state-card">
                <div className="empty-state-mark" aria-hidden="true">✳</div>
                <div>
                  <h3>This workspace is ready</h3>
                  <p>It starts with no assessment records. Assessment conversations will be added in a later step.</p>
                </div>
                <span className="empty-state-status">EMPTY BY DESIGN</span>
              </div>

              {selectedOrganization.role === "administrator" && (
                <section className="invite-card" aria-labelledby="invite-title">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">TEAM ACCESS</p>
                      <h2 id="invite-title">Invite a teammate</h2>
                    </div>
                    <span className="role-badge">ADMIN ONLY</span>
                  </div>
                  <p className="muted-copy">The invitee creates a password using a single-use email link that expires after seven days.</p>
                  <form className="invite-form" onSubmit={submitInvitation}>
                    <label className="visually-hidden" htmlFor="invite-email">Teammate email address</label>
                    <input
                      id="invite-email"
                      type="email"
                      value={inviteEmail}
                      onChange={(event) => setInviteEmail(event.target.value)}
                      placeholder="name@company.com"
                      autoComplete="email"
                      maxLength={254}
                      required
                    />
                    <label className="invite-role-label visually-hidden" htmlFor="invite-role">Role</label>
                    <select
                      id="invite-role"
                      value={inviteRole}
                      onChange={(event) => setInviteRole(event.target.value)}
                    >
                      <option value="consultant">Consultant</option>
                      <option value="representative">Representative</option>
                    </select>
                    <button className="secondary-button" type="submit" disabled={isInviting}>
                      {isInviting ? "Sending…" : "Send invitation"}
                      {!isInviting && <span aria-hidden="true">→</span>}
                    </button>
                  </form>
                </section>
              )}
            </>
          )}

          <InvitationInbox
            invitations={invitations}
            onAccept={acceptPendingInvitation}
            acceptingId={acceptingId}
          />
        </div>
        <div className="conversation-footer">
          <span className="footer-lock" aria-hidden="true">▣</span>
          <span>Organization setup only · Assessment chat is not part of this flow</span>
        </div>
      </section>
    </div>
  );
}
