import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";
import { AuthProvider } from "@/lib/auth-context";
import { ThemeProvider } from "@/lib/theme-provider";
import { AppShell } from "@/components/layout/AppShell";

export const metadata: Metadata = {
  title: "Congress Alpha | Congressional Stock Intelligence & Analytics",
  description:
    "Executive-grade stock disclosure analytics, STOCK Act compliance monitoring, and AI-powered congressional trade surveillance.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // suppressHydrationWarning is required because next-themes sets the theme
    // class on <html> before React hydrates.
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen flex flex-col bg-background font-sans text-foreground antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <AuthProvider>
            <QueryProvider>
              <AppShell>{children}</AppShell>
            </QueryProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
