import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthProvider.jsx";
import { getCurrentAccount } from "./api.js";

const { supabaseMock } = vi.hoisted(() => ({
  supabaseMock: {
    auth: {
      getSession: vi.fn(),
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
});
