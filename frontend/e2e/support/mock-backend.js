const SUPABASE_URL = "http://127.0.0.1:54321";
const ADMIN_TOKEN = "e2e-admin-access-token";
const CONSULTANT_TOKEN = "e2e-consultant-access-token";
const REPRESENTATIVE_TOKEN = "e2e-representative-access-token";
const NOW = "2026-10-26T12:00:00Z";

const defaultOrganization = {
  id: "org-e2e-001",
  name: "Northstar Health",
  sector_code: "healthcare",
  sector: "Healthcare",
  size_code: "mid-market",
  size: "250–500 employees",
  role: "administrator",
};

const control = {
  code: "PR.AA-03",
  title: "Users, services, and hardware are authenticated",
};

function jsonResponse(body, status = 200, headers = {}) {
  return {
    status,
    contentType: "application/json",
    headers,
    body: JSON.stringify(body),
  };
}

function makeAssessment(id, title, organizationId) {
  return {
    id,
    organization_id: organizationId,
    title,
    framework_code: "NIST-CSF",
    framework_version: "2.0",
    kb_version: "demo-0.2",
    status: "in_progress",
    started_at: NOW,
  };
}

function makeScope(assessment, organization) {
  return {
    organization_id: organization.id,
    organization_name: organization.name,
    assessment,
    control_count: 1,
    functions: [
      {
        code: "PR",
        name: "Protect",
        categories: [
          {
            code: "PR.AA",
            name: "Identity Management, Authentication, and Access Control",
            controls: [control],
          },
        ],
      },
    ],
  };
}

function makeInterview(organization, assessment) {
  return {
    organization_id: organization.id,
    organization_name: organization.name,
    assessment_id: assessment.id,
    assessment_title: assessment.title,
    assessment_status: assessment.status,
    participant_id: "participant-e2e-001",
    session: { id: `session-${assessment.id}`, closed: false },
    turns: [
      {
        id: "turn-question-e2e-001",
        sequence_no: 1,
        speaker: "agent",
        participant_id: null,
        turn_type: "question",
        question_id: "question-e2e-001",
        replies_to_turn_id: null,
        content: "How do you manage user access?",
      },
    ],
    in_scope_controls: [{ id: "control-e2e-001", code: control.code, title: control.title }],
    draft_results: [],
    resumed: false,
  };
}

function makePendingReview(assessment) {
  return {
    result_id: "result-e2e-001",
    assessment_id: assessment.id,
    control_code: control.code,
    control_title: control.title,
    control_status: "partially_implemented",
    maturity_current: 2,
    confidence: 0.82,
    explanation: "MFA is enabled for administrator accounts but not all users.",
    evidence_summary: "The uploaded access policy describes the review cadence.",
    requires_human_review: true,
  };
}

function makeReport(state) {
  const organization = state.organizations[0];
  const assessment = state.assessments[0];
  const evidence = state.uploadedEvidence[0];
  const decision = state.decisions[0];

  return {
    organization: {
      id: organization.id,
      name: organization.name,
      sector: organization.sector,
      size: organization.size,
    },
    assessment: {
      id: assessment.id,
      title: assessment.title,
      framework: "NIST CSF 2.0",
      kb_version: assessment.kb_version,
      status: "completed",
      started_at: assessment.started_at,
      completed_at: NOW,
    },
    generated_at: NOW,
    is_demo_data: false,
    scope: [{ code: control.code, title: control.title }],
    results: [
      {
        code: control.code,
        title: control.title,
        control_status: "partially_implemented",
        status_label: "Partially implemented",
        basis: decision?.outcome === "accepted" ? "accepted_agent_result" : "consultant_version",
        reviewed_by: "QA Reviewer",
        reviewed_at: NOW,
        explanation: "MFA is enabled for administrator accounts but not all users.",
        not_assessed_reason: null,
        evidence: evidence
          ? [
              {
                source_type: "document",
                reference: evidence.original_filename,
                excerpt: evidence.extracted_content_preview,
                nature: "implementation",
              },
            ]
          : [],
        evidence_pending: false,
      },
    ],
    pending: [],
    exclusions: [],
    summary: {
      controls_in_scope: 1,
      finalized: 1,
      pending: 0,
      coverage_pct: 100,
      final_with_evidence_pending: 0,
      status_counts: {
        implemented: 0,
        partially_implemented: 1,
        not_implemented: 0,
        not_assessed: 0,
      },
    },
  };
}

function corsHeaders(origin) {
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-headers": "apikey, authorization, content-type, x-client-info",
    "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
  };
}

export async function installMockBackend(page, options = {}) {
  const state = {
    organizations: options.organizations ? [...options.organizations] : [],
    organizationsByToken: {
      [ADMIN_TOKEN]: options.organizations ? [...options.organizations] : [],
      [CONSULTANT_TOKEN]: options.consultantOrganizations ? [...options.consultantOrganizations] : [],
    },
    scopeOrganizationsByUser: options.scopeOrganizationsByUser ?? false,
    assessments: options.assessments ? [...options.assessments] : [],
    invitations: [],
    pendingInvitations: options.pendingInvitations ? [...options.pendingInvitations] : [],
    pendingInvitationRecipientToken: options.pendingInvitationRecipientToken || REPRESENTATIVE_TOKEN,
    acceptedInvitations: [],
    uploadedEvidence: [],
    pendingReviews: [],
    decisions: [],
    interviewsByAssessment: {},
    interviewAnswers: [],
    interviewTurnRequests: [],
    failNextInterviewTurn: options.failNextInterviewTurn ?? false,
    invitedPassword: null,
    apiCalls: [],
    unhandledRequests: [],
    healthFailures: options.healthFailures ?? 0,
    failAssessmentCreation: options.failAssessmentCreation ?? false,
    failEvidenceUpload: options.failEvidenceUpload ?? false,
    assessmentCreateCount: 0,
    evidenceUploadCount: 0,
    usersByToken: {
      [ADMIN_TOKEN]: {
        id: "user-e2e-admin",
        email: "admin@example.test",
        is_platform_admin: true,
      },
      [CONSULTANT_TOKEN]: {
        id: "user-e2e-consultant",
        email: "consultant@example.test",
        is_platform_admin: false,
      },
      [REPRESENTATIVE_TOKEN]: {
        id: "user-e2e-representative",
        email: "representative@example.test",
        is_platform_admin: false,
      },
    },
  };

  await page.route(`${SUPABASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const headers = corsHeaders("http://127.0.0.1:4179");

    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers });
      return;
    }

    if (url.pathname === "/auth/v1/token" && request.method() === "POST") {
      const credentials = request.postDataJSON();
      const isInvitedRepresentative = credentials.email?.toLowerCase() === "representative@example.test";
      const passwordIsValid = credentials.password === "e2e-password"
        || (isInvitedRepresentative && credentials.password === state.invitedPassword);
      if (!passwordIsValid) {
        await route.fulfill(
          jsonResponse(
            {
              code: "invalid_credentials",
              error_code: "invalid_credentials",
              msg: "Invalid login credentials",
            },
            400,
            headers,
          ),
        );
        return;
      }

      const normalizedEmail = credentials.email?.toLowerCase();
      const token = normalizedEmail === "consultant@example.test"
        ? CONSULTANT_TOKEN
        : normalizedEmail === "representative@example.test"
          ? REPRESENTATIVE_TOKEN
          : ADMIN_TOKEN;
      const account = state.usersByToken[token];

      await route.fulfill(
        jsonResponse(
          {
            access_token: token,
            token_type: "bearer",
            expires_in: 3600,
            expires_at: Math.floor(Date.now() / 1000) + 3600,
            refresh_token: "e2e-refresh-token",
            user: {
              id: account.id,
              aud: "authenticated",
              role: "authenticated",
              email: account.email,
              app_metadata: { provider: "email", providers: ["email"] },
              user_metadata: {},
              created_at: NOW,
            },
          },
          200,
          headers,
        ),
      );
      return;
    }

    if (url.pathname === "/auth/v1/logout" && request.method() === "POST") {
      await route.fulfill({ status: 204, headers });
      return;
    }

    if (url.pathname === "/auth/v1/user" && request.method() === "GET") {
      const token = request.headers().authorization?.replace(/^Bearer\s+/i, "");
      const account = state.usersByToken[token] || state.usersByToken[ADMIN_TOKEN];
      await route.fulfill(
        jsonResponse({
          id: account.id,
          email: account.email,
          role: "authenticated",
          app_metadata: { provider: "email", providers: ["email"] },
          user_metadata: {},
        }, 200, headers),
      );
      return;
    }

    state.unhandledRequests.push(`${request.method()} ${url.pathname}`);
    await route.fulfill(jsonResponse({ msg: "Unhandled E2E auth request" }, 404, headers));
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const method = request.method();
    let body = null;

    if (request.headers()["content-type"]?.includes("application/json")) {
      try {
        body = request.postDataJSON();
      } catch {
        body = null;
      }
    }

    state.apiCalls.push({ method, path, body });

    if (path === "/health" && method === "GET") {
      if (state.healthFailures > 0) {
        state.healthFailures -= 1;
        await route.fulfill(jsonResponse({ detail: "API unavailable" }, 503));
      } else {
        await route.fulfill(jsonResponse({ status: "ok" }));
      }
      return;
    }

    if (path === "/auth/me" && method === "GET") {
      const token = request.headers().authorization?.replace(/^Bearer\s+/i, "");
      await route.fulfill(jsonResponse(state.usersByToken[token] || state.usersByToken[ADMIN_TOKEN]));
      return;
    }

    if (path === "/auth/accept-invitation" && method === "POST") {
      const invitation = state.pendingInvitations.find((item) => item.id === "invitation-e2e-001");
      if (!invitation || body?.token !== "e2e-invitation-token") {
        await route.fulfill(jsonResponse({ detail: "Invitation not found." }, 404));
        return;
      }
      const representative = state.usersByToken[REPRESENTATIVE_TOKEN];
      state.invitedPassword = body.password;
      state.organizationsByToken[REPRESENTATIVE_TOKEN] = [
        {
          id: invitation.organization_id,
          name: invitation.organization_name,
          sector_code: "healthcare",
          sector: "Healthcare",
          size_code: "mid-market",
          size: "250–500 employees",
          role: invitation.role,
        },
      ];
      state.acceptedInvitations.push(invitation.id);
      state.pendingInvitations = state.pendingInvitations.filter((item) => item.id !== invitation.id);
      await route.fulfill(jsonResponse({
        invitation_id: invitation.id,
        organization_id: invitation.organization_id,
        email: representative.email,
        role: invitation.role,
        membership_status: "active",
      }));
      return;
    }

    if (path === "/reference-data/industry-sectors" && method === "GET") {
      await route.fulfill(jsonResponse([{ code: "healthcare", label: "Healthcare" }]));
      return;
    }

    if (path === "/reference-data/organization-sizes" && method === "GET") {
      await route.fulfill(jsonResponse([{ code: "mid-market", label: "250–500 employees" }]));
      return;
    }

    if (path === "/organizations" && method === "GET") {
      const token = request.headers().authorization?.replace(/^Bearer\s+/i, "");
      const organizations = state.scopeOrganizationsByUser
        ? state.organizationsByToken[token] || []
        : state.organizations;
      await route.fulfill(jsonResponse(organizations));
      return;
    }

    if (path === "/organizations" && method === "POST") {
      const organization = {
        id: "org-e2e-001",
        name: body.name,
        sector_code: body.sector_code,
        sector: "Healthcare",
        size_code: body.size_code,
        size: "250–500 employees",
        role: "administrator",
      };
      state.organizations = [organization];
      if (state.scopeOrganizationsByUser) {
        const token = request.headers().authorization?.replace(/^Bearer\s+/i, "");
        state.organizationsByToken[token] = [organization];
      }
      await route.fulfill(jsonResponse(organization, 201));
      return;
    }

    if (path === "/organizations/me/invitations" && method === "GET") {
      const token = request.headers().authorization?.replace(/^Bearer\s+/i, "");
      const invitations = !state.scopeOrganizationsByUser || token === state.pendingInvitationRecipientToken
        ? state.pendingInvitations
        : [];
      await route.fulfill(jsonResponse(invitations));
      return;
    }

    const acceptInvitation = path.match(/^\/organizations\/invitations\/([^/]+)\/accept$/);
    if (acceptInvitation && method === "POST") {
      const invitation = state.pendingInvitations.find((item) => item.id === acceptInvitation[1]);
      if (!invitation) {
        await route.fulfill(jsonResponse({ detail: "Invitation not found." }, 404));
        return;
      }
      state.acceptedInvitations.push(invitation.id);
      const joinedOrganization = {
        id: invitation.organization_id,
        name: invitation.organization_name,
        sector_code: "healthcare",
        sector: "Healthcare",
        size_code: "mid-market",
        size: "250–500 employees",
        role: invitation.role,
      };
      if (!state.scopeOrganizationsByUser) {
        state.organizations = [...state.organizations, joinedOrganization];
      }
      if (state.scopeOrganizationsByUser) {
        const token = request.headers().authorization?.replace(/^Bearer\s+/i, "");
        state.organizationsByToken[token] = [
          ...(state.organizationsByToken[token] || []),
          joinedOrganization,
        ];
      }
      state.pendingInvitations = state.pendingInvitations.filter(
        (item) => item.id !== invitation.id,
      );
      await route.fulfill(jsonResponse({ invitation_id: invitation.id }));
      return;
    }

    const invitationOrganization = path.match(/^\/organizations\/([^/]+)\/invitations$/);
    if (invitationOrganization && method === "POST") {
      state.invitations.push({ email: body.email, role: body.role });
      if (state.scopeOrganizationsByUser) {
        const organization = state.organizations.find((item) => item.id === invitationOrganization[1]);
        if (organization) {
          state.pendingInvitations = [{
            id: "invitation-e2e-001",
            organization_id: organization.id,
            organization_name: organization.name,
            role: body.role,
            expires_at: "2026-12-01T00:00:00Z",
          }];
        }
      }
      await route.fulfill(jsonResponse({ email: body.email, expires_in_days: 7 }, 201));
      return;
    }

    const assessmentList = path.match(/^\/organizations\/([^/]+)\/assessments$/);
    if (assessmentList && method === "GET") {
      await route.fulfill(jsonResponse(state.assessments));
      return;
    }

    if (assessmentList && method === "POST") {
      state.assessmentCreateCount += 1;
      if (state.failAssessmentCreation) {
        state.failAssessmentCreation = false;
        await route.fulfill(
          jsonResponse({ detail: "Assessment API is temporarily unavailable." }, 503),
        );
        return;
      }

      const assessment = makeAssessment("assessment-e2e-001", body.title, assessmentList[1]);
      state.assessments = [assessment];
      await route.fulfill(jsonResponse(assessment, 201));
      return;
    }

    const scopeMatch = path.match(/^\/organizations\/([^/]+)\/assessments\/([^/]+)\/scope$/);
    if (scopeMatch && method === "GET") {
      const organization = state.organizations.find((item) => item.id === scopeMatch[1]);
      const assessment = state.assessments.find((item) => item.id === scopeMatch[2]);
      if (!organization || !assessment) {
        await route.fulfill(jsonResponse({ detail: "Organization not found." }, 404));
        return;
      }
      await route.fulfill(jsonResponse(makeScope(assessment, organization)));
      return;
    }

    const interviewPath = path.match(/^\/organizations\/([^/]+)\/assessments\/([^/]+)\/interview(?:\/turns)?$/);
    if (interviewPath && method === "POST" && !path.endsWith("/turns")) {
      const organization = state.organizations.find((item) => item.id === interviewPath[1]);
      const assessment = state.assessments.find((item) => item.id === interviewPath[2]);
      if (!organization || !assessment) {
        await route.fulfill(jsonResponse({ detail: "Interview not found." }, 404));
        return;
      }
      const key = `${organization.id}:${assessment.id}`;
      const existing = state.interviewsByAssessment[key];
      const data = existing ? { ...existing, resumed: true } : makeInterview(organization, assessment);
      state.interviewsByAssessment[key] = { ...data, resumed: false };
      await route.fulfill(jsonResponse(data, existing ? 200 : 201));
      return;
    }

    if (interviewPath && method === "GET") {
      const key = `${interviewPath[1]}:${interviewPath[2]}`;
      const existing = state.interviewsByAssessment[key];
      if (!existing) {
        await route.fulfill(jsonResponse({ detail: "Interview not found." }, 404));
        return;
      }
      await route.fulfill(jsonResponse(existing));
      return;
    }

    if (interviewPath && path.endsWith("/turns") && method === "POST") {
      const key = `${interviewPath[1]}:${interviewPath[2]}`;
      const current = state.interviewsByAssessment[key];
      if (!current) {
        await route.fulfill(jsonResponse({ detail: "Interview not found." }, 404));
        return;
      }
      state.interviewTurnRequests.push(body);
      if (state.failNextInterviewTurn) {
        state.failNextInterviewTurn = false;
        await route.fulfill(jsonResponse({ detail: "The interview assistant is temporarily unavailable." }, 503));
        return;
      }

      const answer = {
        id: "turn-answer-e2e-001",
        sequence_no: 2,
        speaker: "participant",
        participant_id: current.participant_id,
        turn_type: "answer",
        question_id: body.question_id,
        replies_to_turn_id: body.replies_to_turn_id,
        content: body.content,
      };
      const followUp = {
        id: "turn-follow-up-e2e-001",
        sequence_no: 3,
        speaker: "agent",
        participant_id: null,
        turn_type: "follow_up",
        question_id: "question-e2e-002",
        replies_to_turn_id: answer.id,
        content: "Who reviews access rights, and how often?",
      };
      state.interviewAnswers.push(body);
      state.interviewsByAssessment[key] = {
        ...current,
        turns: [...current.turns, answer, followUp],
        resumed: false,
      };
      await route.fulfill(jsonResponse({
        turn: answer,
        agent_turns: [followUp],
        draft_results: [],
        session_closed: false,
        idempotent_replay: false,
      }, 201));
      return;
    }

    if (path === "/evidence/" && method === "POST") {
      state.evidenceUploadCount += 1;
      if (state.failEvidenceUpload) {
        state.failEvidenceUpload = false;
        await route.fulfill(
          jsonResponse({ detail: "Evidence parser is temporarily unavailable." }, 503),
        );
        return;
      }
      const evidence = {
        id: "evidence-e2e-001",
        original_filename: "access-policy.txt",
        extracted_content_preview: "Access reviews are performed quarterly.",
      };
      state.uploadedEvidence = [evidence];
      await route.fulfill(jsonResponse(evidence, 201));
      return;
    }

    if (path === "/expert-reviews/pending" && method === "GET") {
      await route.fulfill(jsonResponse(state.pendingReviews));
      return;
    }

    const reviewEvidence = path.match(/^\/expert-reviews\/([^/]+)\/evidence$/);
    if (reviewEvidence && method === "GET") {
      const evidence = state.uploadedEvidence[0];
      await route.fulfill(
        jsonResponse({
          sources: [],
          linked_documents: evidence
            ? [
                {
                  id: evidence.id,
                  original_filename: evidence.original_filename,
                  size_bytes: 42,
                  content_type: "text/plain",
                  extracted_content_preview: evidence.extracted_content_preview,
                },
              ]
            : [],
          evidence_pending: false,
          skipped_source_count: 0,
        }),
      );
      return;
    }

    const reviewTrace = path.match(/^\/expert-reviews\/([^/]+)\/trace$/);
    if (reviewTrace && method === "GET") {
      await route.fulfill(
        jsonResponse({ result_id: reviewTrace[1], trace: [], linked_decision: null }),
      );
      return;
    }

    const decision = path.match(/^\/expert-reviews\/([^/]+)\/decision$/);
    if (decision && method === "POST") {
      state.decisions.push({ result_id: decision[1], ...body });
      state.pendingReviews = [];
      await route.fulfill(
        jsonResponse({
          result_id: decision[1],
          outcome: body.outcome,
          comment: body.comment,
          message: "Review decision received successfully.",
        }),
      );
      return;
    }

    const reportPdf = path.match(/^\/organizations\/([^/]+)\/assessments\/([^/]+)\/report\.pdf$/);
    if (reportPdf && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: { "content-disposition": 'attachment; filename="qa-report.pdf"' },
        body: Buffer.from("%PDF-1.4\n% E2E report fixture\n%%EOF\n"),
      });
      return;
    }

    const report = path.match(/^\/organizations\/([^/]+)\/assessments\/([^/]+)\/report$/);
    if (report && method === "GET") {
      if (!state.organizations.length || !state.assessments.length) {
        await route.fulfill(jsonResponse({ detail: "Report not found." }, 404));
        return;
      }
      await route.fulfill(jsonResponse(makeReport(state)));
      return;
    }

    state.unhandledRequests.push(`${method} ${path}`);
    await route.fulfill(jsonResponse({ detail: "Unhandled E2E API request." }, 404));
  });

  return state;
}

export const seededOrganization = { ...defaultOrganization };
