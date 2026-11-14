import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.jsx";
import { getOrganization, listOrganizations } from "./features/organizations/api.js";

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

vi.mock("./features/organizations/api.js", () => ({
  listOrganizations: vi.fn(),
  getOrganization: vi.fn().mockResolvedValue(null),
  listMyInvitations: vi.fn().mockResolvedValue([]),
  listIndustrySectors: vi.fn().mockResolvedValue([]),
  listOrganizationSizes: vi.fn().mockResolvedValue([]),
  createOrganization: vi.fn(),
  createInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
  uploadEvidence: vi.fn(),
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
    getOrganization.mockResolvedValue(null);
    window.history.replaceState({}, "", "/");
    listOrganizations.mockResolvedValue([
      { id: "alpha", name: "Alpha", sector: "Other", size: "Unknown", role: "consultant" },
      { id: "beta", name: "Beta", sector: "Other", size: "Unknown", role: "consultant" },
    ]);
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

  it("toggles password visibility without submitting or changing the password", async () => {
    render(<App />);
    await screen.findByText("Backend health check passed");

    const password = screen.getByLabelText("Password", { exact: true });
    expect(password).toHaveAttribute("type", "password");
    fireEvent.change(password, { target: { value: "example-password" } });

    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("example-password");

    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("example-password");
    expect(authMock.signIn).not.toHaveBeenCalled();
  });

  it("preserves the selected workspace when navigating to evidence and back", async () => {
    authMock.user = { accessToken: "token", email: "member@example.com" };
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Beta/ }));
    fireEvent.click(screen.getByRole("link", { name: /Upload evidence/ }));
    expect(window.location.search).toContain("organization_id=beta");
    expect(await screen.findByRole("combobox")).toHaveValue("beta");
    fireEvent.click(screen.getByRole("link", { name: /Back to workspaces/ }));
    expect(await screen.findByRole("heading", { level: 1, name: "Beta" })).toBeInTheDocument();
  });

  it("shows the account role for the selected workspace and updates it on a switch", async () => {
    authMock.user = { id: "member", accessToken: "token", email: "member@example.com" };
    getOrganization.mockImplementation(async (id) => ({
      role: id === "alpha" ? "consultant" : "representative",
    }));
    render(<App />);

    expect(screen.getByText("member@example.com", { selector: ".account-email" })).toBeInTheDocument();
    expect(await screen.findByText("Consultant", { selector: ".account-role" })).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: /Beta/ }));
    expect(await screen.findByText("Representative", { selector: ".account-role" })).toBeInTheDocument();
    expect(screen.queryByText("Consultant", { selector: ".account-role" })).not.toBeInTheDocument();
  });

  it("requires organization selection when opening evidence without context", async () => {
    window.history.replaceState({}, "", "/evidence");
    authMock.user = { accessToken: "token", email: "member@example.com" };
    render(<App />);
    expect(await screen.findByRole("combobox")).toHaveValue("");
    expect(screen.getByRole("button", { name: /Drag and drop a file here/ })).toHaveAttribute("aria-disabled", "true");
  });
});
