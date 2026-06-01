import { test, expect } from "@playwright/test";

/**
 * Unauthenticated smoke — проверяет, что приложение реально грузится и отдаёт
 * брендированную страницу логина без JS-ошибок, на self-hosted Geist.
 *
 * Authed-смоуки (dashboard / company card / financials) требуют тест-аккаунт и
 * прохождение MFA — выносятся отдельно, когда появится seeded test-session
 * (см. backend/tests/conftest auth_header / preview-token).
 */
test.describe("smoke · unauthenticated", () => {
  test("приложение грузится и отдаёт брендированную страницу", async ({ page }) => {
    const resp = await page.goto("/");
    expect(resp, "нет ответа от сервера").not.toBeNull();
    expect(resp!.status(), "HTTP статус").toBeLessThan(400);
    await expect(page).toHaveTitle(/Единая Платформа Трансформации/);
  });

  test("неавторизованного редиректит на форму логина", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.locator('input[type="password"]').first(),
    ).toBeVisible({ timeout: 12_000 });
  });

  test("шрифт Geist реально применён (self-hosted, пункт 1)", async ({ page }) => {
    await page.goto("/");
    const fontFamily = await page.evaluate(
      () => getComputedStyle(document.body).fontFamily,
    );
    expect(fontFamily.toLowerCase()).toContain("geist");
  });

  test("на старте нет JS-ошибок в консоли", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto("/");
    await page.waitForTimeout(2_500);
    // отсеиваем безобидный сетевой шум (favicon, заблокированные внешние ресурсы)
    const jsErrors = errors.filter(
      (e) => !/favicon|net::ERR|Failed to load resource|ERR_CONNECTION/i.test(e),
    );
    expect(jsErrors, jsErrors.join("\n")).toHaveLength(0);
  });
});
