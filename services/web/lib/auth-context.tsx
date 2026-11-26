"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { UserJWTPayload } from "@/types/auth";
import { useRouter } from "next/navigation";

interface LoginResult {
  mfa_required?: boolean;
  mfa_token?: string;
  must_setup_2fa?: boolean;
  /** 2FA is not enabled; tokens are issued and enrollment is optional. */
  mfa_setup_available?: boolean;
  must_change_password?: boolean;
  access_token?: string;
  refresh_token?: string;
  user?: UserJWTPayload;
}

interface AuthContextType {
  user: UserJWTPayload | null;
  token: string | null;
  isAuthenticated: boolean;
  /** True once the stored session has been checked on mount. */
  ready: boolean;
  chamberScope: "House" | "Senate" | "Combined";
  setChamberScope: (scope: "House" | "Senate" | "Combined") => void;
  isChamberLocked: boolean;
  lockedReason?: string;
  timeHorizon: string;
  setTimeHorizon: (horizon: string) => void;
  loginWithCredentials: (username: string, password: string) => Promise<LoginResult>;
  verifyMfaCode: (mfa_token: string, code: string, username?: string) => Promise<boolean>;
  enableMfa: (mfa_token: string, code: string) => Promise<string[]>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isAuthenticated: false,
  ready: false,
  chamberScope: "Combined",
  setChamberScope: () => { },
  isChamberLocked: false,
  timeHorizon: "90 Days",
  setTimeHorizon: () => { },
  loginWithCredentials: async () => ({}),
  verifyMfaCode: async () => false,
  enableMfa: async () => [],
  logout: () => { },
});

/** Map the auth-service `/me` payload to the UI's user shape. */
function mapMe(me: any): UserJWTPayload {
  const roles: string[] = me?.roles || [];
  return {
    sub: me?.username || me?.sub || "",
    username: me?.username || "",
    role: roles.includes("admin") ? "admin" : "user",
    allowed_chambers: me?.allowed_chambers || [],
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<UserJWTPayload | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [chamberScope, setChamberScopeState] = useState<
    "House" | "Senate" | "Combined"
  >("Combined");
  const [timeHorizon, setTimeHorizon] = useState<string>("90 Days");

  const persist = useCallback((t: string, u: UserJWTPayload) => {
    setToken(t);
    setUser(u);
    try {
      localStorage.setItem("congress_jwt", t);
      localStorage.setItem("congress_user", JSON.stringify(u));
    } catch {
      /* ignore */
    }
  }, []);

  const clear = useCallback(() => {
    setToken(null);
    setUser(null);
    try {
      localStorage.removeItem("congress_jwt");
      localStorage.removeItem("congress_user");
    } catch {
      /* ignore */
    }
  }, []);

  const fetchMe = useCallback(
    async (t: string): Promise<UserJWTPayload | null> => {
      try {
        const res = await fetch("/api/auth/me", {
          headers: { Authorization: `Bearer ${t}` },
        });
        if (!res.ok) return null;
        return mapMe(await res.json());
      } catch {
        return null;
      }
    },
    [],
  );

  // Hydrate the session from the stored token on mount.
  useEffect(() => {
    let storedToken: string | null = null;
    try {
      storedToken = localStorage.getItem("congress_jwt");
    } catch {
      storedToken = null;
    }
    if (!storedToken) {
      setReady(true);
      return;
    }
    (async () => {
      const me = await fetchMe(storedToken as string);
      if (me) persist(storedToken as string, me);
      else clear();
      setReady(true);
    })();
  }, [fetchMe, persist, clear]);

  const allowed = user?.allowed_chambers || [];
  const isChamberLocked = allowed.length === 1;
  const lockedReason = isChamberLocked
    ? `Your account permissions are restricted to ${allowed[0]} disclosures only.`
    : undefined;

  // Auto-enforce the chamber lock for single-chamber accounts.
  useEffect(() => {
    const a = user?.allowed_chambers || [];
    if (a.length === 1) {
      const single = a[0] as "House" | "Senate";
      setChamberScopeState((prev) => (prev === single ? prev : single));
    }
  }, [user]);

  const setChamberScope = (scope: "House" | "Senate" | "Combined") => {
    if (isChamberLocked) return;
    setChamberScopeState(scope);
  };

  const loginWithCredentials = async (
    username: string,
    password: string,
  ): Promise<LoginResult> => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Authentication failed");
    }
    if (data.access_token) {
      const me = await fetchMe(data.access_token);
      if (me) persist(data.access_token, me);
    }
    return data;
  };

  const verifyMfaCode = async (
    mfa_token: string,
    code: string,
    _username?: string,
  ): Promise<boolean> => {
    const res = await fetch("/api/auth/mfa/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mfa_token, code }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Invalid 2FA verification code");
    }
    if (data.access_token) {
      const me = await fetchMe(data.access_token);
      if (me) persist(data.access_token, me);
      return true;
    }
    return false;
  };

  const enableMfa = async (
    mfa_token: string,
    code: string,
  ): Promise<string[]> => {
    const res = await fetch("/api/auth/mfa/enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mfa_token, code }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to enable 2FA");
    }
    if (data.access_token) {
      const me = await fetchMe(data.access_token);
      if (me) persist(data.access_token, me);
    }
    return data.recovery_codes || [];
  };

  const logout = () => {
    fetch("/api/auth/logout", { method: "POST" }).catch(() => { });
    clear();
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user && !!token,
        ready,
        chamberScope,
        setChamberScope,
        isChamberLocked,
        lockedReason,
        timeHorizon,
        setTimeHorizon,
        loginWithCredentials,
        verifyMfaCode,
        enableMfa,
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
