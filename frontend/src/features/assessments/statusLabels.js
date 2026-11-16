// Display labels for the assessment status values of the backend (AssessmentStatus in app/schemas/assessments.py).
export const ASSESSMENT_STATUS_LABELS = {
  draft: "Draft",
  in_progress: "In progress",
  awaiting_review: "Awaiting review",
  completed: "Completed",
};

export function assessmentStatusLabel(status) {
  return ASSESSMENT_STATUS_LABELS[status] || status;
}

// Mirrors accepts_interviews() in app/services/assessment_status.py: interviews stay open while the
// assessment is in progress or awaiting review, and close once it is completed.
const INTERVIEW_OPEN_STATUSES = new Set(["in_progress", "awaiting_review"]);

export function acceptsInterviews(status) {
  return INTERVIEW_OPEN_STATUSES.has(status);
}
