"use client";

import * as React from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ThemeProviderProps } from "next-themes";

/**
 * Wraps `next-themes` so the app can switch between light/dark and follow the
 * device preference. `attribute="class"` toggles the `.dark` class that the
 * Tailwind `darkMode: ["class"]` config and `globals.css` rely on.
 */
export function ThemeProvider({ children, ...props }: ThemeProviderProps) {
    return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}