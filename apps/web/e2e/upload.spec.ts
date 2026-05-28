import { test, expect } from "@playwright/test";

test.describe("Core navigation", () => {
  test("renders the dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
  });

  test("renders the live recording page", async ({ page }) => {
    await page.goto("/record");
    await expect(page).toHaveURL(/record/);
  });

  test("renders the upload page", async ({ page }) => {
    await page.goto("/upload");
    await expect(page).toHaveURL(/upload/);
  });

  test("renders the sessions library", async ({ page }) => {
    await page.goto("/sessions");
    await expect(page).toHaveURL(/sessions/);
  });

  test("renders the files browser", async ({ page }) => {
    await page.goto("/files");
    await expect(page).toHaveURL(/files/);
  });
});
