import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OrganizationWorkspace from "./OrganizationWorkspace.jsx";
import {
  acceptInvitation,
  createInvitation,
  createOrganization,
  listIndustrySectors,
  listMyInvitations,
  listOrganizations,
  listOrganizationSizes,
} from "./api.js";

vi.mock("./api.js", () => ({
  acceptInvitation: vi.fn(),
  createInvitation: vi.fn(),
  createOrganization: vi.fn(),
  listIndustrySectors: vi.fn(),
  listMyInvitations: vi.fn(),
  listOrganizations: vi.fn(),
  listOrganizationSizes: vi.fn(),
}));

const existingOrganization = {
  id: "existing-org-id",
  name: "Northstar Health",
  sector_code: "healthcare",
  sector: "Healthcare",
  size_code: "mid-market",
  size: "250–500 employees",
  role: "administrator",
};
const sectors = [{ code: "healthcare", label: "Healthcare" }];
const sizes = [{ code: "mid-market", label: "250–500 employees" }];

describe("OrganizationWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listOrganizations.mockResolvedValue([]);
    listMyInvitations.mockResolvedValue([]);
    listIndustrySectors.mockResolvedValue(sectors);
    listOrganizationSizes.mockResolvedValue(sizes);
  });

  it("requires an explicit duplicate choice before retrying organization creation", async () => {
    createOrganization
      .mockRejectedValueOnce({
        status: 409,
        body: { detail: { code: "duplicate_name_requires_confirmation", matches: [existingOrganization] } },
      })
      .mockResolvedValueOnce({ ...existingOrganization, id: "new-org-id" });
    listOrganizations.mockResolvedValueOnce([]).mockResolvedValueOnce([
      { ...existingOrganization, id: "new-org-id" },
    ]);

    render(<OrganizationWorkspace accessToken="test-token" isPlatformAdmin />);
    await screen.findByRole("heading", { name: "Set up an organization" });
    fireEvent.change(screen.getByLabelText(/Organization name/), { target: { value: "Northstar Health" } });
    fireEvent.change(screen.getByLabelText(/Sector/), { target: { value: "healthcare" } });
    fireEvent.change(screen.getByLabelText(/Organization size/), { target: { value: "mid-market" } });
    fireEvent.click(screen.getByRole("button", { name: /Create workspace/ }));

    const confirmButton = await screen.findByRole("button", {
      name: "Confirm separate workspace for Northstar Health",
    });
    expect(createOrganization).toHaveBeenCalledTimes(1);

    fireEvent.click(confirmButton);
    await waitFor(() => expect(createOrganization).toHaveBeenCalledTimes(2));
    expect(createOrganization).toHaveBeenLastCalledWith({
      name: "Northstar Health",
      sector_code: "healthcare",
      size_code: "mid-market",
      confirm_duplicate_of: "existing-org-id",
    }, "test-token");
    expect(await screen.findByText(/starts empty/)).toBeInTheDocument();
  });

  it("offers a consultant or representative invitation role", async () => {
    listOrganizations.mockResolvedValue([existingOrganization]);

    render(<OrganizationWorkspace accessToken="test-token" />);

    expect(await screen.findByRole("option", { name: "Consultant" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Representative" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send invitation/ })).toBeInTheDocument();
  });

  it("sends a consultant invitation and reports the seven-day activation link", async () => {
    listOrganizations.mockResolvedValue([existingOrganization]);
    createInvitation.mockResolvedValue({ email: "teammate@example.com" });

    render(<OrganizationWorkspace accessToken="test-token" />);

    fireEvent.change(await screen.findByLabelText("Teammate email address"), {
      target: { value: "teammate@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Send invitation/ }));

    expect(createInvitation).toHaveBeenCalledWith(
      existingOrganization.id,
      "teammate@example.com",
      "consultant",
      "test-token",
    );
    expect(await screen.findByText(/invitation email was sent.*expires in seven days/i)).toBeInTheDocument();
  });

  it("accepts a pending invitation and refreshes the organization list", async () => {
    const invitation = {
      id: "invitation-id",
      organization_id: "invited-org-id",
      organization_name: "Invited Client",
      expires_at: "2026-12-01T00:00:00Z",
    };
    const invitedOrganization = {
      ...existingOrganization,
      id: "invited-org-id",
      name: "Invited Client",
      role: "consultant",
    };
    listMyInvitations.mockResolvedValueOnce([invitation]).mockResolvedValueOnce([]);
    listOrganizations.mockResolvedValueOnce([]).mockResolvedValueOnce([invitedOrganization]);
    acceptInvitation.mockResolvedValue({ invitation_id: invitation.id });

    render(<OrganizationWorkspace accessToken="test-token" />);
    fireEvent.click(await screen.findByRole("button", { name: "Accept" }));

    await waitFor(() => {
      expect(acceptInvitation).toHaveBeenCalledWith(invitation.id, "test-token");
      expect(listOrganizations).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText("You joined the organization. It is now available in your workspace list.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Invited Client" })).toBeInTheDocument();
  });
});
