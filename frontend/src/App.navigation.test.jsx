import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.jsx";
import { getOrganization } from "./features/organizations/api.js";

const { authMock } = vi.hoisted(() => ({
  authMock: {
    user: { id: "user-a", email: "admin@example.com", accessToken: "token-a", is_platform_admin: false },
    isLoading: false,
    authError: "",
    signIn: vi.fn(),
    signOut: vi.fn(),
    isSupabaseConfigured: true,
  },
}));

vi.mock("./auth/AuthProvider.jsx", () => ({ useAuth: () => authMock }));
vi.mock("./api/client.js", () => ({ checkApiHealth: vi.fn().mockResolvedValue({}) }));
vi.mock("./features/organizations/api.js", () => ({ getOrganization: vi.fn().mockResolvedValue(null) }));
vi.mock("./features/organizations/OrganizationWorkspace.jsx", () => ({
  default: ({ onOrganizationChange }) => <div>Organizations view
    <button type="button" onClick={() => onOrganizationChange("org-1")}>Select organization</button>
    <button type="button" onClick={() => onOrganizationChange("org-2")}>Switch organization</button>
  </div>,
}));
vi.mock("./features/expertReviews/ExpertReviewWorkspace.jsx", () => ({
  default: () => <div>Expert reviews view</div>,
}));
vi.mock("./features/interviews/InterviewWorkspace.jsx", () => ({
  default: ({ initialOrganizationId, initialAssessmentId }) => (
    <div>Interview view {initialOrganizationId}/{initialAssessmentId}</div>
  ),
}));
vi.mock("./features/reports/ReportWorkspace.jsx", () => ({
  default: () => <div>Reports view</div>,
}));
vi.mock("./features/assessments/AssessmentWorkspace.jsx", () => ({
  default: ({ onStartInterview }) => (
    <div>
      Assessments view
      <button type="button" onClick={() => onStartInterview("org-1", "assessment-1")}>Go to interview</button>
    </div>
  ),
}));
vi.mock("./features/organizations/EvidencePage.jsx", () => ({
  default: ({ onNavigate }) => (
    <div>
      Evidence view
      <button type="button" onClick={() => onNavigate("/")}>Back</button>
    </div>
  ),
}));

function breadcrumb() {
  return document.querySelector(".breadcrumb strong").textContent;
}

describe("App navigation", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
    getOrganization.mockResolvedValue(null);
  });

  it("renders a single navigation list and a single breadcrumb", () => {
    render(<App />);

    const items = document.querySelectorAll(".app-rail .rail-navigation-item");
    expect(Array.from(items).map((node) => node.getAttribute("aria-label"))).toEqual([
      "Client onboarding",
      "Assessments",
      "Interview",
      "Expert reviews",
      "Reports",
    ]);
    expect(screen.getAllByRole("button", { name: "Client onboarding" })).toHaveLength(1);
    expect(document.querySelectorAll(".breadcrumb")).toHaveLength(1);
    expect(screen.queryByText("Later")).not.toBeInTheDocument();
  });

  it("opens the Client onboarding screen by default", () => {
    render(<App />);

    expect(screen.getByText("Organizations view")).toBeInTheDocument();
    expect(breadcrumb()).toBe("Organization setup");
    expect(screen.getByRole("button", { name: "Client onboarding" })).toHaveAttribute("aria-current", "page");
  });

  it("opens the Assessments workspace from the rail", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Assessments" }));

    expect(screen.getByText("Assessments view")).toBeInTheDocument();
    expect(screen.queryByText("Organizations view")).not.toBeInTheDocument();
    expect(breadcrumb()).toBe("Assessments");
    expect(screen.getByRole("button", { name: "Assessments" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Client onboarding" })).not.toHaveAttribute("aria-current");
  });

  it("opens the Expert reviews workspace from the rail", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Expert reviews" }));

    expect(screen.getByText("Expert reviews view")).toBeInTheDocument();
    expect(screen.queryByText("Organizations view")).not.toBeInTheDocument();
    expect(breadcrumb()).toBe("Expert reviews");
    expect(screen.getByRole("button", { name: "Expert reviews" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Client onboarding" })).not.toHaveAttribute("aria-current");
  });

  it("opens the Interview screen from the rail", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Interview" }));

    expect(screen.getByText(/Interview view/)).toBeInTheDocument();
    expect(screen.queryByText("Organizations view")).not.toBeInTheDocument();
    expect(breadcrumb()).toBe("Interview");
    expect(screen.getByRole("button", { name: "Interview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Client onboarding" })).not.toHaveAttribute("aria-current");
  });

  it("opens the interview of an assessment chosen on the Assessments screen", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Assessments" }));
    fireEvent.click(screen.getByRole("button", { name: "Go to interview" }));

    expect(screen.getByText("Interview view org-1/assessment-1")).toBeInTheDocument();
    expect(breadcrumb()).toBe("Interview");
    expect(screen.getByRole("button", { name: "Interview" })).toHaveAttribute("aria-current", "page");
  });

  it("keeps the legacy evidence URL available without a navigation tab", () => {
    window.history.replaceState({}, "", "/evidence");
    render(<App />);

    expect(screen.getByText("Evidence view")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/evidence");
    expect(breadcrumb()).toBe("Evidence upload");
    expect(screen.queryByRole("link", { name: "Evidence upload" })).not.toBeInTheDocument();
  });

  it("keeps every screen reachable when switching back and forth", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Expert reviews" }));
    expect(screen.getByText("Expert reviews view")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Client onboarding" }));
    expect(screen.getByText("Organizations view")).toBeInTheDocument();
    expect(breadcrumb()).toBe("Organization setup");
  });

  it("does not show a standalone evidence shortcut", () => {
    render(<App />);
    expect(screen.queryByRole("link", { name: /Upload evidence/ })).not.toBeInTheDocument();
  });

  it("opens the Reports workspace from the rail", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Reports" }));

    expect(screen.getByText("Reports view")).toBeInTheDocument();
    expect(screen.queryByText("Organizations view")).not.toBeInTheDocument();
    expect(breadcrumb()).toBe("Reports");
    expect(screen.getByRole("button", { name: "Reports" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Client onboarding" })).not.toHaveAttribute("aria-current");
  });

  it("navigates back to / and opens the Reports view when clicking Reports from the evidence page", async () => {
    render(<App />);

    window.history.pushState({}, "", "/evidence");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(await screen.findByText("Evidence view")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/evidence");

    fireEvent.click(screen.getByRole("button", { name: "Reports" }));
    expect(screen.getByText("Reports view")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
    expect(breadcrumb()).toBe("Reports");
    expect(screen.getByRole("button", { name: "Reports" })).toHaveAttribute("aria-current", "page");
  });

  it("uses the selected organization's role for navigation and theme", async () => {
    getOrganization.mockImplementation(async (id) => ({
      id, name: id === "org-1" ? "Alpha" : "Beta",
      role: id === "org-1" ? "representative" : "consultant",
    }));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Select organization" }));
    await waitFor(() => expect(document.querySelector(".app-shell")).toHaveClass("role-representative"));
    expect(screen.queryByRole("button", { name: "Expert reviews" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Client onboarding" })).not.toBeInTheDocument();
    expect(breadcrumb()).toBe("Organizations");
    expect(screen.getByRole("button", { name: "Assessments" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Interview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reports" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Switch organization" }));
    await waitFor(() => expect(document.querySelector(".app-shell")).not.toHaveClass("role-representative"));
    expect(screen.getByRole("button", { name: "Expert reviews" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Client onboarding" })).toBeInTheDocument();
  });

  it("restores default navigation if the organization role request fails", async () => {
    getOrganization.mockRejectedValueOnce(new Error("Network unavailable"));
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Select organization" }));
    expect(screen.queryByRole("button", { name: "Expert reviews" })).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole("button", { name: "Expert reviews" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Client onboarding" })).toBeInTheDocument();
  });
});
