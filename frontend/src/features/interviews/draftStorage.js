// Keeps an unsent interview answer in this tab so that signing in again after an expired session
// does not lose it. The request id is kept with it: resending the same answer reuses the same
// client_request_id, so the server stores it at most once even if the first attempt got through.
const PREFIX = "agrc.interview-draft:";

function storage() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function loadInterviewDraft(sessionId) {
  try {
    const raw = storage()?.getItem(PREFIX + sessionId);
    const draft = raw ? JSON.parse(raw) : null;
    return typeof draft?.content === "string" ? draft : null;
  } catch {
    return null;
  }
}

export function saveInterviewDraft(sessionId, draft) {
  try {
    if (draft?.content) {
      storage()?.setItem(PREFIX + sessionId, JSON.stringify(draft));
    } else {
      storage()?.removeItem(PREFIX + sessionId);
    }
  } catch {
    // Storage can be unavailable (private mode, blocked site data); the draft then lives only in memory.
  }
}

export function clearInterviewDrafts() {
  try {
    const store = storage();
    if (!store) return;
    Object.keys(store)
      .filter((key) => key.startsWith(PREFIX))
      .forEach((key) => store.removeItem(key));
  } catch {
    // Nothing to clear.
  }
}
