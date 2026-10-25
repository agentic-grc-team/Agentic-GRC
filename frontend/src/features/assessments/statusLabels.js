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
