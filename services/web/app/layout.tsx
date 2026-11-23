import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";
import { AuthProvider } from "@/lib/auth-context";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { ChatDrawer } from "@/components/chat/ChatDrawer";

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
    <html lang="en" className="dark">
      <body className="min-h-screen flex flex-col bg-background font-sans text-foreground antialiased">
        <AuthProvider>
          <QueryProvider>
            <Header />
            <main className="flex-1 pb-16">{children}</main>
            <Footer />
            <ChatDrawer />
          </QueryProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
