"use client";

import React, { useState, useEffect } from "react";
import { Activity, Shield, CheckCircle2 } from "lucide-react";

export function Footer() {
  const [timestamp, setTimestamp] = useState<string>("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const formatted = now.toLocaleDateString("en-US", {
        month: "short",
        day: "2-digit",
        year: "numeric",
      }) + " · " + now.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZoneName: "short",
      });
      setTimestamp(formatted);
    };

    updateTime();
    const interval = setInterval(updateTime, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <footer className="w-full border-t border-border/40 bg-card/60 py-3 text-xs text-muted-foreground">
      <div className="mx-auto flex max-w-7xl flex-col sm:flex-row items-center justify-between px-4 sm:px-6 lg:px-8 gap-2">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-emerald-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="font-medium text-foreground">Operational</span>
          </div>
          <span className="text-border">|</span>
          <span className="flex items-center gap-1">
            <Shield className="h-3 w-3 text-muted-foreground" />
            STOCK Act Compliance Monitoring Active
          </span>
        </div>

        <div className="flex items-center gap-4 text-[11px]">
          <span>
            Cluster Health: <span className="font-mono text-emerald-400 font-semibold">6 / 6 Services UP</span>
          </span>
          <span className="text-border">|</span>
          <span>
            Last Synced: <span className="font-mono text-foreground">{timestamp || "Nov 23, 2026 · 06:30 UTC"}</span>
          </span>
        </div>
      </div>
    </footer>
  );
}
