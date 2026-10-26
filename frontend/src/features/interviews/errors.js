export function describeInterviewError(error) {
  const status = error?.status;
  if (status === 401) {
    return "Your session has expired. Sign in again to continue.";
  }
  if (status === 403) {
    return "You do not have permission to take part in this interview.";
  }
  if (status === 404) {
    return "This interview was not found, or you do not have access to it.";
  }
  if (status === 503) {
    return "The interview assistant is unavailable right now. Your answer is still in the box, so you can try again.";
  }
  return error?.message || "Something went wrong. Try again.";
}

export function isRetryableInterviewError(error) {
  return error?.status === undefined || error?.status === 503;
}
