import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.jsx";

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
vi.mock("./features/organizations/OrganizationWorkspace.jsx", () => ({
  default: () => <div>Organizations view</div>,
}));
vi.mock("./features/expertReviews/ExpertReviewWorkspace.jsx", () => ({
  default: () => <div>Expert reviews view</div>,
}));
vi.mock("./features/interviews/InterviewWorkspace.jsx", () => ({
  default: () => <div>Interview view</div>,
}));
vi.mock("./features/reports/ReportWorkspace.jsx", () => ({
  default: () => <div>Reports view</div>,
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
  });

  it("renders a single navigation list and a single breadcrumb", () => {
    render(<App />);

    const items = document.querySelectorAll(".app-rail .rail-navigation-item");
    expect(Array.from(items).map((node) => node.getAttribute("aria-label"))).toEqual([
      "Client onboarding",
      "Interview",
      "Expert reviews",
      "Reports",
      "Evidence upload",
    ]);
    expect(screen.getAllByRole("button", { name: "Client onboarding" })).toHaveLength(1);
    expect(document.querySelectorAll(".breadcrumb")).toHaveLength(1);
    expect(screen.queryByText(/Assessments/)).not.toBeInTheDocument();
    expect(screen.queryByText("Later")).not.toBeInTheDocument();
  });

  it("opens the Client onboarding screen by default", () => {
    render(<App />);

    expect(screen.getByText("Organizations view")).toBeInTheDocument();
    expect(breadcrumb()).toBe("Organization setup");
    expect(screen.getByRole("button", { name: "Client onboarding" })).toHaveAttribute("aria-current", "page");
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

    expect(screen.getByText("Interview view")).toBeInTheDocument();
    expect(screen.queryByText("Organizations view")).not.toBeInTheDocument();
    expect(breadcrumb()).toBe("Interview");
    expect(screen.getByRole("button", { name: "Interview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Client onboarding" })).not.toHaveAttribute("aria-current");
  });

  it("opens the Evidence upload page from the rail", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("link", { name: "Evidence upload" }));

    expect(screen.getByText("Evidence view")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/evidence");
    expect(breadcrumb()).toBe("Evidence upload");
    expect(screen.getByRole("link", { name: "Evidence upload" })).toHaveAttribute("aria-current", "page");
  });

  it("keeps every screen reachable when switching back and forth", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Expert reviews" }));
    expect(screen.getByText("Expert reviews view")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Evidence upload" }));
    expect(screen.getByText("Evidence view")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/evidence");

    fireEvent.click(screen.getByRole("button", { name: "Expert reviews" }));
    expect(screen.getByText("Expert reviews view")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");

    fireEvent.click(screen.getByRole("button", { name: "Client onboarding" }));
    expect(screen.getByText("Organizations view")).toBeInTheDocument();
    expect(breadcrumb()).toBe("Organization setup");
  });

  it("opens the evidence page from the home link and returns from it", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("link", { name: /Upload evidence/ }));
    expect(screen.getByText("Evidence view")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByText("Organizations view")).toBeInTheDocument();
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

  it("navigates back to / and opens the Reports view when clicking Reports from the evidence page", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("link", { name: "Evidence upload" }));
    expect(screen.getByText("Evidence view")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/evidence");

    fireEvent.click(screen.getByRole("button", { name: "Reports" }));
    expect(screen.getByText("Reports view")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
    expect(breadcrumb()).toBe("Reports");
    expect(screen.getByRole("button", { name: "Reports" })).toHaveAttribute("aria-current", "page");
  });
});
