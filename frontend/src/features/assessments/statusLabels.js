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

// The backend decides whether an assessment accepts interviews (accepts_interviews in the
// assessment response), so the rule lives in one place: app/services/assessment_status.py.
export function acceptsInterviews(assessment) {
  return Boolean(assessment?.accepts_interviews);
}
