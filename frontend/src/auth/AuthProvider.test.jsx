import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "../api/client.js";
import { loadInterviewDraft, saveInterviewDraft } from "../features/interviews/draftStorage.js";
import { AuthProvider, SESSION_EXPIRED_MESSAGE, useAuth } from "./AuthProvider.jsx";
import { getCurrentAccount } from "./api.js";

const { supabaseMock } = vi.hoisted(() => ({
  supabaseMock: {
    auth: {
      getSession: vi.fn(),
      refreshSession: vi.fn(),
      onAuthStateChange: vi.fn(),
      signInWithPassword: vi.fn(),
      signInWithOAuth: vi.fn(),
      signOut: vi.fn(),
    },
  },
}));

vi.mock("./supabase.js", () => ({
  getSupabaseClient: () => supabaseMock,
  isSupabaseConfigured: () => true,
}));

vi.mock("./api.js", () => ({
  acceptInvitationProfile: vi.fn(),
  getCurrentAccount: vi.fn(),
}));

function AuthProbe() {
  const { user, authError, signIn, signInWithGoogle, signOut } = useAuth();
  return (
    <div>
      <span>{user?.email || "signed out"}</span>
      <span data-testid="token">{user?.accessToken || ""}</span>
      {authError && <span role="alert">{authError}</span>}
      <button type="button" onClick={() => void signIn("admin@example.com", "password").catch(() => {})}>Sign in</button>
      <button type="button" onClick={() => void signInWithGoogle().catch(() => {})}>Google</button>
      <button type="button" onClick={() => void signOut()}>Sign out</button>
    </div>
  );
}

const session = {
  access_token: "supabase-access-token",
  expires_at: Math.floor((Date.now() + 60_000) / 1000),
  user: { id: "user-1", email: "admin@example.com" },
};

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    supabaseMock.auth.getSession.mockResolvedValue({ data: { session: null }, error: null });
    supabaseMock.auth.onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
    supabaseMock.auth.signOut.mockResolvedValue({ error: null });
  });

  it("uses Supabase email/password sign-in and attaches its access token to the API profile", async () => {
    supabaseMock.auth.signInWithPassword.mockResolvedValue({ data: { session }, error: null });
    getCurrentAccount.mockResolvedValue({
      id: "user-1",
      email: "admin@example.com",
      is_platform_admin: true,
    });
    render(<AuthProvider><AuthProbe /></AuthProvider>);

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("admin@example.com")).toBeInTheDocument();
    expect(supabaseMock.auth.signInWithPassword).toHaveBeenCalledWith({
      email: "admin@example.com",
      password: "password",
    });
    expect(getCurrentAccount).toHaveBeenCalledWith("supabase-access-token");
  });

  it("shares a simultaneous profile lookup triggered by session restore and auth event", async () => {
    let onAuthChange;
    let resolveAccount;
    getCurrentAccount.mockReturnValue(new Promise((resolve) => { resolveAccount = resolve; }));
    supabaseMock.auth.getSession.mockResolvedValue({ data: { session }, error: null });
    supabaseMock.auth.onAuthStateChange.mockImplementation((callback) => {
      onAuthChange = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    onAuthChange("INITIAL_SESSION", session);

    await waitFor(() => expect(getCurrentAccount).toHaveBeenCalledTimes(1));
    resolveAccount({ id: "user-1", email: "admin@example.com" });
    expect(await screen.findByText("admin@example.com")).toBeInTheDocument();
    await act(async () => {
      onAuthChange("SIGNED_IN", session);
      await Promise.resolve();
    });
    expect(getCurrentAccount).toHaveBeenCalledTimes(1);
  });

  it("starts Google OAuth through Supabase with the application callback URL", async () => {
    supabaseMock.auth.signInWithOAuth.mockResolvedValue({ data: {}, error: null });
    render(<AuthProvider><AuthProbe /></AuthProvider>);

    fireEvent.click(screen.getByRole("button", { name: "Google" }));

    await waitFor(() => expect(supabaseMock.auth.signInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    }));
  });

  it("removes the local Supabase session on sign out", async () => {
    supabaseMock.auth.signInWithPassword.mockResolvedValue({ data: { session }, error: null });
    getCurrentAccount.mockResolvedValue({
      id: "user-1",
      email: "admin@example.com",
      is_platform_admin: true,
    });
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByText("admin@example.com");

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(screen.getByText("signed out")).toBeInTheDocument());
    expect(supabaseMock.auth.signOut).toHaveBeenCalledOnce();
  });

  it("shows a safe sign-in error when Supabase rejects credentials", async () => {
    supabaseMock.auth.signInWithPassword.mockResolvedValue({
      data: { session: null },
      error: { code: "invalid_credentials", message: "invalid_credentials" },
    });
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    expect(getCurrentAccount).not.toHaveBeenCalled();
  });

  describe("session renewal", () => {
    const account = { id: "user-1", email: "admin@example.com", is_platform_admin: false };
    let emitAuthEvent;

    function reply(status, body = {}) {
      return { status, ok: status >= 200 && status < 300, json: async () => body };
    }

    async function renderSignedIn() {
      supabaseMock.auth.onAuthStateChange.mockImplementation((callback) => {
        emitAuthEvent = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      });
      supabaseMock.auth.getSession.mockResolvedValue({ data: { session }, error: null });
      getCurrentAccount.mockResolvedValue(account);
      render(<AuthProvider><AuthProbe /></AuthProvider>);
      await screen.findByText("admin@example.com");
      expect(screen.getByTestId("token")).toHaveTextContent("supabase-access-token");
    }

    it("swaps a refreshed token in place without looking the account up again", async () => {
      await renderSignedIn();

      act(() => emitAuthEvent("TOKEN_REFRESHED", { ...session, access_token: "refreshed-token" }));

      expect(screen.getByTestId("token")).toHaveTextContent("refreshed-token");
      expect(screen.getByText("admin@example.com")).toBeInTheDocument();
      expect(getCurrentAccount).toHaveBeenCalledTimes(1);
    });

    it("renews a token Supabase rejected and retries the request", async () => {
      await renderSignedIn();
      supabaseMock.auth.refreshSession.mockResolvedValue({
        data: { session: { ...session, access_token: "renewed-token" } },
        error: null,
      });
      fetch.mockResolvedValueOnce(reply(401)).mockResolvedValueOnce(reply(200, { ok: true }));

      await expect(apiRequest("/organizations", { accessToken: "supabase-access-token" })).resolves.toEqual({ ok: true });

      expect(supabaseMock.auth.refreshSession).toHaveBeenCalledOnce();
      expect(fetch.mock.calls[1][1].headers.get("Authorization")).toBe("Bearer renewed-token");
      expect(supabaseMock.auth.signOut).not.toHaveBeenCalled();
    });

    it("uses a token Supabase already renewed without forcing another refresh", async () => {
      await renderSignedIn();
      supabaseMock.auth.getSession.mockResolvedValue({
        data: { session: { ...session, access_token: "already-renewed" } },
        error: null,
      });
      fetch.mockResolvedValueOnce(reply(401)).mockResolvedValueOnce(reply(200, {}));

      await apiRequest("/organizations", { accessToken: "supabase-access-token" });

      expect(supabaseMock.auth.refreshSession).not.toHaveBeenCalled();
      expect(fetch.mock.calls[1][1].headers.get("Authorization")).toBe("Bearer already-renewed");
    });

    it("signs out locally with a clear message when the session cannot be renewed", async () => {
      await renderSignedIn();
      saveInterviewDraft("session-1", { content: "Unsent answer", pending: null, turnId: "turn-1" });
      supabaseMock.auth.refreshSession.mockResolvedValue({
        data: { session: null },
        error: { status: 400, message: "Invalid Refresh Token" },
      });
      fetch.mockResolvedValueOnce(reply(401));

      await expect(apiRequest("/organizations", { accessToken: "supabase-access-token" })).rejects.toMatchObject({ status: 401 });
      act(() => emitAuthEvent("SIGNED_OUT", null));

      expect(await screen.findByRole("alert")).toHaveTextContent(SESSION_EXPIRED_MESSAGE);
      await waitFor(() => expect(screen.getByText("signed out")).toBeInTheDocument());
      expect(supabaseMock.auth.signOut).toHaveBeenCalledWith({ scope: "local" });
      // The unsent answer survives so the interview can resume after signing in again.
      expect(loadInterviewDraft("session-1")?.content).toBe("Unsent answer");
    });

    it("keeps the user signed in when the refresh fails for a network reason", async () => {
      await renderSignedIn();
      supabaseMock.auth.refreshSession.mockResolvedValue({
        data: { session: null },
        error: { status: 0, message: "Failed to fetch" },
      });
      fetch.mockResolvedValueOnce(reply(401));

      await expect(apiRequest("/organizations", { accessToken: "supabase-access-token" })).rejects.toMatchObject({ status: 401 });

      expect(supabaseMock.auth.signOut).not.toHaveBeenCalled();
      expect(screen.getByText("admin@example.com")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("keeps the user signed in when getSession cannot refresh an expired token for a network reason", async () => {
      await renderSignedIn();
      supabaseMock.auth.getSession.mockResolvedValue({
        data: { session: null },
        error: { status: 0, message: "Failed to fetch" },
      });
      fetch.mockResolvedValueOnce(reply(401));

      await expect(apiRequest("/organizations", { accessToken: "supabase-access-token" })).rejects.toMatchObject({ status: 401 });

      expect(supabaseMock.auth.refreshSession).not.toHaveBeenCalled();
      expect(supabaseMock.auth.signOut).not.toHaveBeenCalled();
      expect(screen.getByText("admin@example.com")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("signs out when getSession reports that Supabase rejected the session", async () => {
      await renderSignedIn();
      supabaseMock.auth.getSession.mockResolvedValue({
        data: { session: null },
        error: { status: 400, message: "Invalid Refresh Token" },
      });
      fetch.mockResolvedValueOnce(reply(401));

      await expect(apiRequest("/organizations", { accessToken: "supabase-access-token" })).rejects.toMatchObject({ status: 401 });

      expect(supabaseMock.auth.signOut).toHaveBeenCalledWith({ scope: "local" });
      expect(await screen.findByRole("alert")).toHaveTextContent(SESSION_EXPIRED_MESSAGE);
    });

    it("clears unsent interview answers on an explicit sign out", async () => {
      await renderSignedIn();
      saveInterviewDraft("session-1", { content: "Unsent answer", pending: null, turnId: "turn-1" });

      fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

      await waitFor(() => expect(screen.getByText("signed out")).toBeInTheDocument());
      expect(loadInterviewDraft("session-1")).toBeNull();
    });
  });
});
