"use client";

import { redirect } from "next/navigation";

export default function MfaPage() {
  // Direct redirect to /login which manages full 2FA challenge and setup states
  redirect("/login");
}
