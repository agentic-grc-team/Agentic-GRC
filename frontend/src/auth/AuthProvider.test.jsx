import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client.js";
import { AuthProvider, useAuth } from "./AuthProvider.jsx";
import { getCurrentAccount, signInWithPassword } from "./api.js";

vi.mock("./api.js", () => ({
  getCurrentAccount: vi.fn(),
  signInWithPassword: vi.fn(),
}));

function AuthProbe() {
  const { user, authError, signIn, signOut } = useAuth();
  return (
    <div>
      <span>{user?.email || "signed out"}</span>
      {authError && <span role="alert">{authError}</span>}
      <button type="button" onClick={() => void signIn("admin@example.com", "password").catch(() => {})}>Sign in</button>
      <button type="button" onClick={signOut}>Sign out</button>
    </div>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
  });

  it("stores a successful email/password session for the current browser tab", async () => {
    signInWithPassword.mockResolvedValue({
      access_token: "signed-token",
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      user: { id: "user-1", email: "admin@example.com", is_platform_admin: true },
    });
    render(<AuthProvider><AuthProbe /></AuthProvider>);

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("admin@example.com")).toBeInTheDocument();
    const savedSession = JSON.parse(window.sessionStorage.getItem("agentic-grc.session.v1"));
    expect(savedSession.accessToken).toBe("signed-token");
    expect(signInWithPassword).toHaveBeenCalledWith("admin@example.com", "password");
  });

  it("removes the browser session on sign out", async () => {
    signInWithPassword.mockResolvedValue({
      access_token: "signed-token",
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      user: { id: "user-1", email: "admin@example.com", is_platform_admin: true },
    });
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByText("admin@example.com");

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(screen.getByText("signed out")).toBeInTheDocument());
    expect(window.sessionStorage.getItem("agentic-grc.session.v1")).toBeNull();
  });

  it("shows a clear error when the API rejects credentials", async () => {
    signInWithPassword.mockRejectedValue(new ApiError(401, { detail: "Email or password is incorrect." }));
    render(<AuthProvider><AuthProbe /></AuthProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    expect(getCurrentAccount).not.toHaveBeenCalled();
  });
});
