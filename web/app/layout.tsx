import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/lib/providers";

export const metadata: Metadata = {
    title: "Congressional Disclosure Analytics",
    description:
        "Chamber-scoped analytics, RAG search, and administration for U.S. congressional financial disclosures.",
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en" suppressHydrationWarning>
            <body className="min-h-screen bg-background antialiased">
                <Providers>{children}</Providers>
            </body>
        </html>
    );
}
