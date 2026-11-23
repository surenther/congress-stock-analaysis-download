import { redirect } from "next/navigation";

/**
 * Root route. The middleware performs the real role/scope-based landing; this
 * is a safe default that sends unauthenticated visitors to the login page.
 */
export default function HomePage() {
    redirect("/dashboard");
}
