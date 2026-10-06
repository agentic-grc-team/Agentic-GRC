import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client.js";
import { AuthProvider } from "./AuthProvider.jsx";
import { acceptInvitationProfile, signInWithPassword } from "./api.js";
import InvitationActivation from "./InvitationActivation.jsx";

vi.mock("./api.js", () => ({
  acceptInvitationProfile: vi.fn(),
  getCurrentAccount: vi.fn(),
  signInWithPassword: vi.fn(),
}));

describe("InvitationActivation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    window.history.replaceState({}, "", "/invite/accept#token=single-use-invitation-token-123456");
  });

  afterEach(() => {
    window.history.replaceState({}, "", "/");
  });

  it("accepts the email token, creates the profile, and signs the invitee in", async () => {
    acceptInvitationProfile.mockResolvedValue({ email: "invitee@example.com" });
    signInWithPassword.mockResolvedValue({
      access_token: "new-user-token",
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      user: { id: "invitee-1", email: "invitee@example.com", is_platform_admin: false },
    });

    render(<AuthProvider><InvitationActivation /></AuthProvider>);
    fireEvent.change(screen.getByLabelText(/Create a password/), {
      target: { value: "a-secure-password-12" },
    });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "a-secure-password-12" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Your account is ready for invitee@example.com.");
    expect(acceptInvitationProfile).toHaveBeenCalledWith(
      "single-use-invitation-token-123456",
      "a-secure-password-12",
    );
    expect(signInWithPassword).toHaveBeenCalledWith("invitee@example.com", "a-secure-password-12");
  });

  it("directs an existing account to sign in and accept from its workspace", async () => {
    acceptInvitationProfile.mockRejectedValue(new ApiError(409, { detail: "Account already exists." }));
    render(<AuthProvider><InvitationActivation /></AuthProvider>);
    fireEvent.change(screen.getByLabelText(/Create a password/), {
      target: { value: "a-secure-password-12" },
    });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "a-secure-password-12" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("An account already exists");
    expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute("href", "/");
  });
});
