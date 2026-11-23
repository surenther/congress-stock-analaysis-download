export interface UserJWTPayload {
  sub: string;
  role: "admin" | "user";
  allowed_chambers: string[]; // ["House"] or ["Senate"] or ["House", "Senate"]
  exp?: number;
  iat?: number;
  username?: string;
}

export interface UserAccount {
  id: string;
  username: string;
  email: string;
  role: "admin" | "user";
  allowed_chambers: string[];
  two_factor_enabled: boolean;
  created_at: string;
  last_login?: string;
}

export interface ClusterServiceHealth {
  name: string;
  port: number;
  status: "healthy" | "unhealthy" | "checking" | "unknown";
  endpoint: string;
  latency_ms?: number;
  details?: any;
}
