import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client.js";
import { getCurrentAccount } from "./api.js";
import { getSupabaseClient, isSupabaseConfigured } from "./supabase.js";

const AuthContext = createContext(null);

function accountFromSession(account, session) {
  const expirySeconds = session.expires_at || Math.floor(Date.now() / 1000) + 3600;
  return {
    ...account,
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

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      setAuthError("Supabase Auth is not configured. Add the frontend environment values and restart Vite.");
      setIsLoading(false);
      return undefined;
    }

    const supabase = getSupabaseClient();
    let isMounted = true;
    let latestRequest = 0;

    async function loadSession(session) {
      const requestId = ++latestRequest;
      if (!session?.access_token) {
        if (isMounted) {
          setUser(null);
          setIsLoading(false);
        }
        return;
      }

      try {
        const account = await getCurrentAccount(session.access_token);
        if (isMounted && requestId === latestRequest) {
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

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
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
      const account = await getCurrentAccount(data.session.access_token);
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
        options: { redirectTo: `${window.location.origin}/auth/callback` },
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
    setUser(null);
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
