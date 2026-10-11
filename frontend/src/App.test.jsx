import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.jsx";

const { authMock } = vi.hoisted(() => ({
  authMock: {
    user: null,
    isLoading: false,
    authError: "",
    signIn: vi.fn(),
    signInWithGoogle: vi.fn(),
    signOut: vi.fn(),
    isSupabaseConfigured: true,
  },
}));

vi.mock("./auth/AuthProvider.jsx", () => ({
  useAuth: () => authMock,
}));

vi.mock("./api/client.js", () => ({
  checkApiHealth: vi.fn().mockResolvedValue({}),
}));

describe("App sign-in options", () => {
  beforeEach(() => {
    Object.assign(authMock, {
      user: null,
      isLoading: false,
      authError: "",
      isSupabaseConfigured: true,
    });
    vi.clearAllMocks();
  });

  it("shows Google sign-in as pending and prevents starting OAuth", () => {
    render(<App />);

    const googleButton = screen.getByRole("button", {
      name: "Continue with Google, pending configuration",
    });

    expect(googleButton).toBeDisabled();
    expect(screen.getByText("Pending")).toBeInTheDocument();

    fireEvent.click(googleButton);

    expect(authMock.signInWithGoogle).not.toHaveBeenCalled();
  });
});
