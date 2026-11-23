import { expect, test } from "@playwright/test";

/**
 * End-to-end smoke test for the authentication entry point (FR-1.1).
 * Requires the full stack running and a provisioned account.
 */
test("login page renders the controlled authentication entry", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByLabel("Username")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
});

test("unauthenticated dashboard access redirects to login", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
});
