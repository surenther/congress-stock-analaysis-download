"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { UserJWTPayload } from "@/types/auth";

interface AuthContextType {
  user: UserJWTPayload | null;
  token: string | null;
  chamberScope: "House" | "Senate" | "Combined";
  setChamberScope: (scope: "House" | "Senate" | "Combined") => void;
  isChamberLocked: boolean;
  lockedReason?: string;
  timeHorizon: string;
  setTimeHorizon: (horizon: string) => void;
  loginAs: (role: "admin" | "user", chambers: string[]) => void;
  logout: () => void;
}

const defaultUser: UserJWTPayload = {
  sub: "admin-exec",
  username: "Executive Analyst",
  role: "admin",
  allowed_chambers: ["House", "Senate"],
};

const AuthContext = createContext<AuthContextType>({
  user: defaultUser,
  token: "mock-jwt-token",
  chamberScope: "Combined",
  setChamberScope: () => {},
  isChamberLocked: false,
  timeHorizon: "90 Days",
  setTimeHorizon: () => {},
  loginAs: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserJWTPayload | null>(defaultUser);
  const [token, setToken] = useState<string | null>("mock-jwt-token");
  const [chamberScope, setChamberScopeState] = useState<"House" | "Senate" | "Combined">("Combined");
  const [timeHorizon, setTimeHorizon] = useState<string>("90 Days");

  // Load from localStorage on mount if available
  useEffect(() => {
    try {
      const stored = localStorage.getItem("congress_user");
      const storedToken = localStorage.getItem("congress_jwt");
      if (stored) {
        const parsed = JSON.parse(stored);
        setUser(parsed);
      }
      if (storedToken) {
        setToken(storedToken);
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
    if (isChamberLocked) return; // Prevent changing if locked
    setChamberScopeState(scope);
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
    setUser(null);
    setToken(null);
    try {
      localStorage.removeItem("congress_user");
      localStorage.removeItem("congress_jwt");
    } catch {}
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        chamberScope,
        setChamberScope,
        isChamberLocked,
        lockedReason,
        timeHorizon,
        setTimeHorizon,
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
