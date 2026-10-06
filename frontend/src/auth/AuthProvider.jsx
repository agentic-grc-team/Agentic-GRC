import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client.js";
import { getCurrentAccount, signInWithPassword } from "./api.js";
import { clearSession, readSession, saveSession } from "./session.js";

const AuthContext = createContext(null);

function accountFromLogin(response) {
  return {
    ...response.user,
    accessToken: response.access_token,
    expiresAt: response.expires_at,
  };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    let isMounted = true;
    const storedSession = readSession();
    if (!storedSession) {
      setIsLoading(false);
      return () => {
        isMounted = false;
      };
    }

    setUser({ ...storedSession.user, accessToken: storedSession.accessToken, expiresAt: storedSession.expiresAt });
    getCurrentAccount(storedSession.accessToken)
      .then((account) => {
        if (isMounted) {
          const refreshedUser = { ...account, accessToken: storedSession.accessToken, expiresAt: storedSession.expiresAt };
          setUser(refreshedUser);
          saveSession({ ...storedSession, user: account });
        }
      })
      .catch((error) => {
        if (isMounted && error instanceof ApiError && error.status === 401) {
          clearSession();
          setUser(null);
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!user?.expiresAt) {
      return undefined;
    }
    const millisecondsUntilExpiry = Date.parse(user.expiresAt) - Date.now();
    if (millisecondsUntilExpiry <= 0) {
      clearSession();
      setUser(null);
      setAuthError("Your session expired. Sign in again to continue.");
      return undefined;
    }
    const timeout = window.setTimeout(() => {
      clearSession();
      setUser(null);
      setAuthError("Your session expired. Sign in again to continue.");
    }, millisecondsUntilExpiry);
    return () => window.clearTimeout(timeout);
  }, [user?.expiresAt]);

  const signIn = useCallback(async (email, password) => {
    setAuthError("");
    try {
      const response = await signInWithPassword(email.trim(), password);
      const nextUser = accountFromLogin(response);
      saveSession({
        accessToken: response.access_token,
        expiresAt: response.expires_at,
        user: response.user,
      });
      setUser(nextUser);
      return nextUser;
    } catch (error) {
      const message = error?.status === 401
        ? "Email or password is incorrect."
        : error?.status === 429
          ? "Too many sign-in attempts. Please wait before trying again."
          : error?.message || "Sign-in could not be completed. Please try again.";
      setAuthError(message);
      throw error;
    }
  }, []);

  const signOut = useCallback(() => {
    clearSession();
    setUser(null);
    setAuthError("");
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, authError, signIn, signOut, clearAuthError: () => setAuthError("") }),
    [authError, isLoading, signIn, signOut, user],
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
