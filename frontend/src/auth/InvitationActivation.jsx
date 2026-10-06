import { useEffect, useState } from "react";

import { ApiError } from "../api/client.js";
import { acceptInvitationProfile } from "./api.js";
import { useAuth } from "./AuthProvider.jsx";

function readActivationToken() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  return fragment.get("token") || new URLSearchParams(window.location.search).get("token") || "";
}

export default function InvitationActivation() {
  const [token] = useState(readActivationToken);
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAccepted, setIsAccepted] = useState(false);
  const [acceptedEmail, setAcceptedEmail] = useState("");
  const { signIn } = useAuth();

  useEffect(() => {
    if (window.location.hash || window.location.search) {
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (password !== passwordConfirmation) {
      setError("The passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    let invitationAccepted = false;
    try {
      const accepted = await acceptInvitationProfile(token, password);
      invitationAccepted = true;
      await signIn(accepted.email, password);
      setAcceptedEmail(accepted.email);
      setIsAccepted(true);
    } catch (acceptError) {
      if (acceptError instanceof ApiError && acceptError.status === 409) {
        setError("An account already exists for this email. Sign in, then accept this invitation from your workspace.");
      } else if (acceptError instanceof ApiError && acceptError.status === 410) {
        setError("This invitation has expired. Ask an organization administrator to send a new one.");
      } else if (acceptError instanceof ApiError && acceptError.status === 404) {
        setError("This invitation link is invalid or has already been used.");
      } else if (acceptError?.status === 401) {
        setError("Your account was created, but automatic sign-in failed. Please sign in from the home page.");
      } else if (invitationAccepted) {
        setError("The invitation was accepted, but automatic sign-in failed. Please sign in from the home page.");
      } else {
        setError(acceptError?.message || "The invitation could not be accepted. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="activation-page">
      <div className="activation-card">
        <div className="login-core" aria-hidden="true">AG</div>
        <p className="eyebrow">ORGANIZATION INVITATION</p>
        <h1>Join Agentic GRC</h1>
        {!token ? (
          <>
            <p className="login-description">This link is missing its invitation token. Open the full link from your email or ask an administrator to send a new invitation.</p>
            <a className="secondary-button" href="/">Return to sign in</a>
          </>
        ) : isAccepted ? (
          <>
            <p className="alert alert-success" role="status">Your account is ready for {acceptedEmail}.</p>
            <a className="primary-button activation-continue" href="/">Continue to your workspace</a>
          </>
        ) : (
          <>
            <p className="login-description">Create your profile with the email address that received the invitation. The link can be used once and expires after seven days.</p>
            {error && <p className="inline-error" role="alert">{error}</p>}
            <form className="activation-form" onSubmit={submit}>
              <label>
                Create a password
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  required
                />
                <span className="field-hint">Use 12–128 characters.</span>
              </label>
              <label>
                Confirm password
                <input
                  type="password"
                  value={passwordConfirmation}
                  onChange={(event) => setPasswordConfirmation(event.target.value)}
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  required
                />
              </label>
              <button className="primary-button sign-in-button" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Creating your account…" : "Accept invitation"}
                {!isSubmitting && <span aria-hidden="true">→</span>}
              </button>
            </form>
            {(error.includes("already exists") || error.includes("Please sign in")) && <a className="text-button activation-signin-link" href="/">Go to sign in</a>}
          </>
        )}
      </div>
    </main>
  );
}
