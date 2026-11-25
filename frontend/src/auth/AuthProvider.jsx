import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, setAccessTokenRefresher } from "../api/client.js";
import { toBrowserPath } from "../basePath.js";
import { clearInterviewDrafts } from "../features/interviews/draftStorage.js";
import { getCurrentAccount } from "./api.js";
import { getSupabaseClient, isSupabaseConfigured } from "./supabase.js";

const AuthContext = createContext(null);
const ACCOUNT_REUSE_MS = 30_000;

function getAccountOnce(accessToken, requestRef) {
  const existing = requestRef.current;
  if (existing?.accessToken === accessToken && Date.now() < existing.expiresAt) {
    return existing.request;
  }
  const request = getCurrentAccount(accessToken);
  const entry = { accessToken, request, expiresAt: Infinity };
  requestRef.current = entry;
  void request.then(
    () => {
      if (requestRef.current === entry) entry.expiresAt = Date.now() + ACCOUNT_REUSE_MS;
    },
    () => {
      if (requestRef.current === entry) requestRef.current = null;
    },
  );
  return request;
}

export const SESSION_EXPIRED_MESSAGE =
  "Your session has expired. Sign in again to continue where you left off.";

function isSessionRejected(error) {
  return error?.status >= 400 && error?.status < 500;
}

function accountFromSession(account, session) {
  const expirySeconds = session.expires_at || Math.floor(Date.now() / 1000) + 3600;
  const { display_name, full_name, name } = session.user?.user_metadata ?? {};
  return {
    ...account,
    displayName: [display_name, full_name, name].find(
      (value) => typeof value === "string" && value.trim(),
    )?.trim() || "",
    accessToken: session.access_token,
    expiresAt: new Date(expirySeconds * 1000).toISOString(),
  };
}

function messageForAuthError(error) {
  if (error instanceof ApiError && error.status === 429) {
    return "Too many sign-in attempts. Please wait before trying again.";
  }
  if (error?.code === "invalid_credentials" || error?.code === "user_not_found") {
    return "Email or password is incorrect.";
  }
  return error?.message || "Sign-in could not be completed. Please try again.";
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const accountRequestRef = useRef(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      setAuthError("Supabase Auth is not configured. Add the frontend environment values and restart Vite.");
      setIsLoading(false);
      return undefined;
    }

    const supabase = getSupabaseClient();
    let isMounted = true;
    let latestRequest = 0;
    let loadedUserId = null;

    function endExpiredSession() {
      if (isMounted) {
        setAuthError(SESSION_EXPIRED_MESSAGE);
      }
      void supabase.auth.signOut({ scope: "local" });
    }

    // Called by the API client after a 401. getSession() renews a token that is about to expire;
    // if it still returns the rejected token, force a refresh. When the session cannot be renewed,
    // sign out locally so the user gets the login screen instead of a dead workspace.
    // getSession() also refreshes an already-expired token itself, so either call can fail for a
    // network reason or a 5xx. Only a 4xx means Supabase rejected the session; anything else keeps
    // the user signed in and lets the request fail as it is, so it can be retried.
    async function refreshAccessToken(staleToken) {
      const { data, error } = await supabase.auth.getSession();
      if (error && !isSessionRejected(error)) {
        return null;
      }
      let session = error ? null : data.session;
      if (session?.access_token === staleToken) {
        const refreshed = await supabase.auth.refreshSession();
        if (refreshed.error) {
          if (!isSessionRejected(refreshed.error)) {
            return null;
          }
          session = null;
        } else {
          session = refreshed.data.session;
        }
      }
      if (!session?.access_token) {
        endExpiredSession();
        return null;
      }
      return session.access_token;
    }
    const unregisterRefresher = setAccessTokenRefresher(refreshAccessToken);

    async function loadSession(session) {
      const requestId = ++latestRequest;
      if (!session?.access_token) {
        loadedUserId = null;
        accountRequestRef.current = null;
        if (isMounted) {
          setUser(null);
          setIsLoading(false);
        }
        return;
      }

      try {
        const account = await getAccountOnce(session.access_token, accountRequestRef);
        if (isMounted && requestId === latestRequest) {
          loadedUserId = session.user?.id ?? account.id;
          setUser(accountFromSession(account, session));
          setAuthError("");
        }
      } catch (error) {
        if (isMounted && requestId === latestRequest) {
          if (error instanceof ApiError && error.status === 401) {
            setUser(null);
            void supabase.auth.signOut({ scope: "local" });
          } else {
            setAuthError(error?.message || "Could not verify the active session with the API.");
          }
        }
      } finally {
        if (isMounted && requestId === latestRequest) {
          setIsLoading(false);
        }
      }
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      // A refreshed token belongs to the account already loaded: swap the token in place rather
      // than looking the account up again, so a failed lookup cannot leave the old token in use.
      if (event === "TOKEN_REFRESHED" && session?.access_token && loadedUserId && session.user?.id === loadedUserId) {
        ++latestRequest;
        setUser((current) => (current ? accountFromSession(current, session) : current));
        return;
      }
      queueMicrotask(() => void loadSession(session));
    });

    const callbackError = new URLSearchParams(window.location.search).get("error_description");
    if (callbackError) {
      setAuthError("Google sign-in could not be completed. Please try again.");
    }

    void supabase.auth.getSession()
      .then(({ data, error }) => {
        if (!isMounted) {
          return;
        }
        if (error) {
          setAuthError("Could not restore your Supabase session. Please sign in again.");
          setIsLoading(false);
          return;
        }
        void loadSession(data.session);
      })
      .catch(() => {
        if (isMounted) {
          setAuthError("Could not restore your Supabase session. Please sign in again.");
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
      unregisterRefresher();
      subscription.unsubscribe();
    };
  }, []);

  const signIn = useCallback(async (email, password) => {
    setAuthError("");
    try {
      const supabase = getSupabaseClient();
      const { data, error } = await supabase.auth.signInWithPassword({
        email: email.trim().toLowerCase(),
        password,
      });
      if (error) {
        throw error;
      }
      if (!data.session) {
        throw new Error("Supabase did not return an authenticated session.");
      }
      const account = await getAccountOnce(data.session.access_token, accountRequestRef);
      const nextUser = accountFromSession(account, data.session);
      setUser(nextUser);
      return nextUser;
    } catch (error) {
      setAuthError(messageForAuthError(error));
      throw error;
    }
  }, []);

  const signInWithGoogle = useCallback(async () => {
    setAuthError("");
    try {
      const { error } = await getSupabaseClient().auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}${toBrowserPath("/auth/callback")}` },
      });
      if (error) {
        throw error;
      }
    } catch (error) {
      setAuthError(messageForAuthError(error));
      throw error;
    }
  }, []);

  const signOut = useCallback(async () => {
    setAuthError("");
    accountRequestRef.current = null;
    setUser(null);
    clearInterviewDrafts();
    if (isSupabaseConfigured()) {
      await getSupabaseClient().auth.signOut();
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      isLoading,
      authError,
      signIn,
      signInWithGoogle,
      signOut,
      clearAuthError: () => setAuthError(""),
      isSupabaseConfigured: isSupabaseConfigured(),
    }),
    [authError, isLoading, signIn, signInWithGoogle, signOut, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return auth;
}
