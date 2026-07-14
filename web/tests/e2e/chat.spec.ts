import { test, expect } from "@playwright/test";

test.describe("AnonyMus E2E Auth & Chat Flow", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the base URL
    await page.goto("/");
  });

  test("should render the auth page with correct branding", async ({ page }) => {
    // Check main title
    await expect(page.locator("h1")).toHaveText("AnonyMus");
    // Check subtitle
    await expect(page.locator("text=Privacy-first encrypted messaging over Tor")).toBeVisible();
  });

  test("should allow switching between Sign In and Create Account tabs", async ({ page }) => {
    const signInTab = page.locator("#tab-login");
    const createAccountTab = page.locator("#tab-register");
    const submitBtn = page.locator("#auth-submit");

    // Verify default state
    await expect(signInTab).toHaveAttribute("aria-selected", "true");
    await expect(submitBtn).toHaveText("Sign In");

    // Click Create Account
    await createAccountTab.click();
    await expect(createAccountTab).toHaveAttribute("aria-selected", "true");
    await expect(signInTab).toHaveAttribute("aria-selected", "false");
    await expect(submitBtn).toHaveText("Create Account");

    // Switch back
    await signInTab.click();
    await expect(signInTab).toHaveAttribute("aria-selected", "true");
    await expect(submitBtn).toHaveText("Sign In");
  });

  test("should show validation errors on form submission with invalid inputs", async ({ page }) => {
    const submitBtn = page.locator("#auth-submit");

    // Attempt submission with empty fields (native HTML validation should block it)
    await submitBtn.click();

    // Username input
    const usernameInput = page.locator("#auth-username");
    await expect(usernameInput).toHaveJSProperty("validity.valueMissing", true);
  });
});
