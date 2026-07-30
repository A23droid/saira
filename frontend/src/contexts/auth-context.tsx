"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import {
  AuthUser,
  getCurrentUserRequest,
  loginRequest,
  logoutRequest,
  registerRequest,
  updateProfileRequest,
  uploadAvatarRequest,
} from "@/lib/api/auth";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  provider: AuthUser["provider"];
  avatarUrl: string | null;
  avatarInitial: string;
  createdAt: string;
}

interface AuthContextValue {
  user: SessionUser | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  updateProfile: (name: string) => Promise<void>;
  uploadAvatar: (file: File) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function toSessionUser(user: AuthUser): SessionUser {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    provider: user.provider,
    avatarUrl: user.avatar_url,
    avatarInitial: user.name.trim().charAt(0).toUpperCase() || "?",
    createdAt: user.created_at,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const loadUser = useCallback(async () => {
    try {
      const current = await getCurrentUserRequest();
      setUser(toSessionUser(current));
      setStatus("authenticated");
    } catch {
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  // Restores the session on first load (and on full page refresh) by asking
  // the backend who the cookie belongs to — this is what makes auth persist
  // across reloads without ever touching localStorage.
  useEffect(() => {
    let cancelled = false;

    getCurrentUserRequest()
      .then((current) => {
        if (cancelled) return;
        setUser(toSessionUser(current));
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        setUser(null);
        setStatus("unauthenticated");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const current = await loginRequest(email, password);
    setUser(toSessionUser(current));
    setStatus("authenticated");
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const current = await registerRequest(name, email, password);
    setUser(toSessionUser(current));
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } catch {
      // Logging out should never get "stuck" client-side even if the
      // network call fails — clear local state regardless.
    }
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  // Both of these update local state directly from the response body,
  // rather than re-fetching /me — so a name edit or avatar upload shows up
  // everywhere the user appears (sidebar, dashboard, profile) immediately,
  // with no manual refresh.
  const updateProfile = useCallback(async (name: string) => {
    const current = await updateProfileRequest(name);
    setUser(toSessionUser(current));
  }, []);

  const uploadAvatar = useCallback(async (file: File) => {
    const current = await uploadAvatarRequest(file);
    setUser(toSessionUser(current));
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        status,
        login,
        register,
        logout,
        refreshUser: loadUser,
        updateProfile,
        uploadAvatar,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
