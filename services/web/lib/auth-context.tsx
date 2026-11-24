"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { UserJWTPayload } from "@/types/auth";
import { useRouter } from "next/navigation";

interface LoginResult {
  mfa_required?: boolean;
  mfa_token?: string;
  must_setup_2fa?: boolean;
  must_change_password?: boolean;
  access_token?: string;
  refresh_token?: string;
  user?: UserJWTPayload;
}

interface AuthContextType {
  user: UserJWTPayload | null;
  token: string | null;
  isAuthenticated: boolean;
  chamberScope: "House" | "Senate" | "Combined";
  setChamberScope: (scope: "House" | "Senate" | "Combined") => void;
  isChamberLocked: boolean;
  lockedReason?: string;
  timeHorizon: string;
  setTimeHorizon: (horizon: string) => void;
  loginWithCredentials: (username: string, password: string) => Promise<LoginResult>;
  verifyMfaCode: (mfa_token: string, code: string, username?: string) => Promise<boolean>;
  loginAs: (role: "admin" | "user", chambers: string[]) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isAuthenticated: false,
  chamberScope: "Combined",
  setChamberScope: () => {},
  isChamberLocked: false,
  timeHorizon: "90 Days",
  setTimeHorizon: () => {},
  loginWithCredentials: async () => ({}),
  verifyMfaCode: async () => false,
  loginAs: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<UserJWTPayload | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [chamberScope, setChamberScopeState] = useState<"House" | "Senate" | "Combined">("Combined");
  const [timeHorizon, setTimeHorizon] = useState<string>("90 Days");

  // Load from localStorage on mount if available
  useEffect(() => {
    try {
      const stored = localStorage.getItem("congress_user");
      const storedToken = localStorage.getItem("congress_jwt");
      if (stored && storedToken) {
        const parsed = JSON.parse(stored);
        setUser(parsed);
        setToken(storedToken);
      } else {
        // Default initialized session for seamless exploratory review
        const initialUser: UserJWTPayload = {
          sub: "admin-exec",
          username: "Executive Analyst",
          role: "admin",
          allowed_chambers: ["House", "Senate"],
        };
        setUser(initialUser);
        setToken("initial-session-token");
        localStorage.setItem("congress_user", JSON.stringify(initialUser));
        localStorage.setItem("congress_jwt", "initial-session-token");
      }
    } catch {
      // ignore
    }
  }, []);

  // Determine if chamber is locked by JWT allowed_chambers claim
  const allowed = user?.allowed_chambers || ["House", "Senate"];
  const isChamberLocked = allowed.length === 1;
  const lockedReason = isChamberLocked
    ? `Your account permissions are restricted to ${allowed[0]} disclosures only.`
    : undefined;

  // Auto-enforce chamber lock if restricted
  useEffect(() => {
    if (allowed.length === 1) {
      const single = allowed[0] as "House" | "Senate";
      if (chamberScope !== single) {
        setChamberScopeState(single);
      }
    }
  }, [allowed, chamberScope]);

  const setChamberScope = (scope: "House" | "Senate" | "Combined") => {
    if (isChamberLocked) return;
    setChamberScopeState(scope);
  };

  const loginWithCredentials = async (username: string, password: string): Promise<LoginResult> => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Authentication failed");
    }

    // If direct token issued without 2FA
    if (data.access_token) {
      const role = (username.toLowerCase().includes("admin") ? "admin" : "user") as "admin" | "user";
      const chambers = role === "admin" ? ["House", "Senate"] : ["House"];
      const loggedUser: UserJWTPayload = {
        sub: username,
        username,
        role,
        allowed_chambers: chambers,
      };
      setUser(loggedUser);
      setToken(data.access_token);
      localStorage.setItem("congress_user", JSON.stringify(loggedUser));
      localStorage.setItem("congress_jwt", data.access_token);
    }

    return data;
  };

  const verifyMfaCode = async (mfa_token: string, code: string, username?: string): Promise<boolean> => {
    const res = await fetch("/api/auth/mfa/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mfa_token, code, username }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Invalid 2FA verification code");
    }

    if (data.access_token) {
      const role = ((username || "").toLowerCase().includes("admin") ? "admin" : "user") as "admin" | "user";
      const chambers = role === "admin" ? ["House", "Senate"] : ["House"];
      const loggedUser: UserJWTPayload = data.user || {
        sub: username || "analyst",
        username: username || "Executive Analyst",
        role,
        allowed_chambers: chambers,
      };
      setUser(loggedUser);
      setToken(data.access_token);
      localStorage.setItem("congress_user", JSON.stringify(loggedUser));
      localStorage.setItem("congress_jwt", data.access_token);
      return true;
    }

    return false;
  };

  const loginAs = (role: "admin" | "user", chambers: string[]) => {
    const newUser: UserJWTPayload = {
      sub: `${role}-demo-id`,
      username: role === "admin" ? "Lead Oversight Admin" : "House Research Fellow",
      role,
      allowed_chambers: chambers,
    };
    setUser(newUser);
    const mockToken = `bearer-jwt-${role}-${chambers.join("-")}`;
    setToken(mockToken);
    try {
      localStorage.setItem("congress_user", JSON.stringify(newUser));
      localStorage.setItem("congress_jwt", mockToken);
    } catch {}

    if (chambers.length === 1) {
      setChamberScopeState(chambers[0] as "House" | "Senate");
    } else {
      setChamberScopeState("Combined");
    }
  };

  const logout = () => {
    fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    setUser(null);
    setToken(null);
    try {
      localStorage.removeItem("congress_user");
      localStorage.removeItem("congress_jwt");
    } catch {}
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user && !!token,
        chamberScope,
        setChamberScope,
        isChamberLocked,
        lockedReason,
        timeHorizon,
        setTimeHorizon,
        loginWithCredentials,
        verifyMfaCode,
        loginAs,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
