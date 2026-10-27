import { expect, test } from "@playwright/test";

import { AssessmentPage } from "./pages/assessment.page.js";
import { LoginPage } from "./pages/login.page.js";
import { OnboardingPage } from "./pages/onboarding.page.js";
import { installMockBackend, seededOrganization } from "./support/mock-backend.js";

const representativeInvitation = {
  id: "invitation-interview-001",
  organization_id: "org-interview-001",
  organization_name: "Northstar Health",
  role: "representative",
  expires_at: "2026-12-01T00:00:00Z",
};

const inProgressAssessment = {
  id: "assessment-interview-001",
  organization_id: representativeInvitation.organization_id,
  title: "NIST CSF baseline",
  framework_code: "NIST-CSF",
  framework_version: "2.0",
  kb_version: "demo-0.2",
  status: "in_progress",
  started_at: "2026-10-26T09:00:00Z",
};

async function startInterviewFromAssessments(page) {
  await page.getByRole("button", { name: "Go to interview" }).click();
  await expect(page.getByRole("heading", { name: "Interview" })).toBeVisible();
  await page.getByRole("button", { name: "Start or resume interview" }).click();
  return page.getByRole("log", { name: "Interview conversation" });
}

async function answerFirstQuestion(page, answer) {
  await page.getByLabel("Your answer").fill(answer);
  await page.getByRole("button", { name: "Send answer" }).click();
  const conversation = page.getByRole("log", { name: "Interview conversation" });
  await expect(conversation).toContainText(answer);
  await expect(conversation).toContainText("Who reviews access rights, and how often?");
}

test("organization invitation and assessment lead the representative into an interview", async ({ page }) => {
  const backend = await installMockBackend(page, { scopeOrganizationsByUser: true });
  const login = new LoginPage(page);

  await login.open();
  await login.signIn();

  const onboarding = new OnboardingPage(page);
  await expect(page.getByRole("heading", { name: "Set up an organization" })).toBeVisible();
  await onboarding.createOrganization("Northstar Health");
  await expect(page.getByRole("heading", { level: 1, name: "Northstar Health" })).toBeVisible();

  await onboarding.invite("representative@example.test", "representative");
  await expect(page.getByRole("status")).toContainText("invitation email was sent");

  const assessments = new AssessmentPage(page);
  await assessments.open();
  await assessments.create("NIST CSF baseline");
  await expect(page.getByText("PR.AA-03")).toBeVisible();
  await expect(page.getByText("demo-0.2")).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Email address")).toBeVisible();
  await page.goto("/invite/accept?token=e2e-invitation-token");
  await page.getByLabel("Create a password").fill("representative-password-1");
  await page.getByLabel("Confirm password").fill("representative-password-1");
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page.getByRole("status")).toContainText("account is ready for representative@example.test");
  await page.getByRole("link", { name: "Continue to your workspace" }).click();
  await page.getByRole("button", { name: "Client onboarding" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Northstar Health" })).toBeVisible();

  await assessments.open();
  await expect(page.getByRole("heading", { name: "NIST CSF baseline" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "New assessment title" })).toHaveCount(0);

  const conversation = await startInterviewFromAssessments(page);
  await expect(conversation).toContainText("How do you manage user access?");
  await answerFirstQuestion(page, "We use MFA for administrator accounts.");

  expect(backend.organizations).toHaveLength(1);
  expect(backend.invitations).toEqual([
    { email: "representative@example.test", role: "representative" },
  ]);
  expect(backend.acceptedInvitations).toEqual(["invitation-e2e-001"]);
  expect(backend.assessments[0].title).toBe("NIST CSF baseline");
  expect(backend.interviewAnswers).toHaveLength(1);
  expect(backend.interviewAnswers[0]).toMatchObject({
    session_id: "session-assessment-e2e-001",
    content: "We use MFA for administrator accounts.",
    question_id: "question-e2e-001",
    replies_to_turn_id: "turn-question-e2e-001",
  });

  await page.reload();
  await page.getByRole("button", { name: "Interview" }).click();
  await page.getByRole("button", { name: "Start or resume interview" }).click();
  const resumedConversation = page.getByRole("log", { name: "Interview conversation" });
  await expect(resumedConversation).toContainText("We use MFA for administrator accounts.");
  await expect(resumedConversation).toContainText("Who reviews access rights, and how often?");
  expect(backend.unhandledRequests).toEqual([]);
});

test("invited representative accepts organization access and answers the interview", async ({ page }) => {
  const backend = await installMockBackend(page, {
    pendingInvitations: [representativeInvitation],
    assessments: [inProgressAssessment],
  });
  const login = new LoginPage(page);

  await login.open();
  await login.signIn("representative@example.test");
  await expect(page.getByRole("heading", { name: "Waiting for your response" })).toBeVisible();

  await new OnboardingPage(page).acceptInvitation();
  await expect(page.getByRole("status")).toContainText("You joined the organization.");

  await new AssessmentPage(page).open();
  await expect(page.getByRole("heading", { name: "NIST CSF baseline" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "New assessment title" })).toHaveCount(0);
  await expect(page.getByText(/An administrator or consultant creates assessments/)).toBeVisible();

  const conversation = await startInterviewFromAssessments(page);
  await expect(conversation).toContainText("How do you manage user access?");
  await answerFirstQuestion(page, "We review access requests with each team lead.");

  expect(backend.acceptedInvitations).toEqual([representativeInvitation.id]);
  expect(backend.interviewAnswers).toHaveLength(1);
  expect(backend.interviewAnswers[0].content).toBe("We review access requests with each team lead.");
  expect(backend.unhandledRequests).toEqual([]);
});

test("keeps an interview answer available and retries it after an assistant outage", async ({ page }) => {
  const organization = { ...seededOrganization, id: "org-retry-001", role: "representative" };
  const assessment = { ...inProgressAssessment, organization_id: organization.id };
  const backend = await installMockBackend(page, {
    organizations: [organization],
    assessments: [assessment],
    failNextInterviewTurn: true,
  });

  const login = new LoginPage(page);
  await login.open();
  await login.signIn("consultant@example.test");
  await new AssessmentPage(page).open();
  await expect(page.getByRole("heading", { name: assessment.title })).toBeVisible();
  const conversation = await startInterviewFromAssessments(page);
  await expect(conversation).toContainText("How do you manage user access?");

  const answer = "MFA is required for privileged accounts.";
  await page.getByLabel("Your answer").fill(answer);
  await page.getByRole("button", { name: "Send answer" }).click();
  await expect(page.getByRole("alert")).toContainText("assistant is unavailable");
  await expect(page.getByLabel("Your answer")).toHaveValue(answer);
  await page.getByRole("button", { name: "Retry sending" }).click();
  await expect(conversation).toContainText("Who reviews access rights, and how often?");

  expect(backend.interviewTurnRequests).toHaveLength(2);
  expect(backend.interviewTurnRequests[1].client_request_id)
    .toBe(backend.interviewTurnRequests[0].client_request_id);
  expect(backend.interviewAnswers).toHaveLength(1);
  expect(backend.unhandledRequests).toEqual([]);
});
