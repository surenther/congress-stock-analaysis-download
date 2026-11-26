"use client";

import * as React from "react";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { Sun, Moon, Monitor, Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const OPTIONS = [
    { value: "light", label: "Light", icon: Sun },
    { value: "dark", label: "Dark", icon: Moon },
    { value: "system", label: "System", icon: Monitor },
] as const;

interface ThemeToggleProps {
    /** Use `full` inside the mobile menu for a full-width row. */
    variant?: "compact" | "full";
    className?: string;
}

export function ThemeToggle({ variant = "compact", className }: ThemeToggleProps) {
    const { theme, setTheme } = useTheme();
    const [mounted, setMounted] = useState(false);
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    // Avoid rendering theme-dependent markup during SSR to prevent hydration
    // mismatches; next-themes only knows the resolved theme on the client.
    useEffect(() => setMounted(true), []);

    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) {
                setOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const active = mounted ? theme ?? "system" : "system";
    const ActiveIcon =
        OPTIONS.find((o) => o.value === active)?.icon ?? Monitor;

    if (variant === "full") {
        return (
            <div className={cn(className)}>
                <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase text-muted-foreground">
                    <Sun className="h-3 w-3" /> Theme
                </div>
                <div className="flex items-center rounded-lg border border-border/40 bg-muted/40 p-1">
                    {OPTIONS.map((opt) => {
                        const Icon = opt.icon;
                        const isSelected = active === opt.value;
                        return (
                            <button
                                key={opt.value}
                                type="button"
                                onClick={() => setTheme(opt.value)}
                                className={cn(
                                    "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-all",
                                    isSelected
                                        ? "bg-emerald-500 text-white font-semibold shadow-sm"
                                        : "text-muted-foreground hover:text-foreground"
                                )}
                            >
                                <Icon className="h-3.5 w-3.5" />
                                {opt.label}
                            </button>
                        );
                    })}
                </div>
            </div>
        );
    }

    return (
        <div ref={ref} className={cn("relative", className)}>
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-label="Change theme"
                aria-expanded={open}
                className="flex items-center gap-1.5 rounded-lg border border-border/50 bg-card px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-accent"
            >
                <ActiveIcon className="h-3.5 w-3.5 text-muted-foreground" />
                <ChevronDown className="h-3 w-3 text-muted-foreground" />
            </button>

            {open && (
                <div className="absolute right-0 z-50 mt-1 w-36 rounded-lg border border-border bg-card p-1 shadow-lg">
                    {OPTIONS.map((opt) => {
                        const Icon = opt.icon;
                        const isSelected = active === opt.value;
                        return (
                            <button
                                key={opt.value}
                                type="button"
                                onClick={() => {
                                    setTheme(opt.value);
                                    setOpen(false);
                                }}
                                className={cn(
                                    "flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs transition-colors",
                                    isSelected
                                        ? "bg-emerald-500/10 text-emerald-500 font-semibold"
                                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                )}
                            >
                                <Icon className="h-3.5 w-3.5" />
                                <span className="flex-1 text-left">{opt.label}</span>
                                {isSelected && <Check className="h-3 w-3" />}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}