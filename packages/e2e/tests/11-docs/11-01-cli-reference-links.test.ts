import { test, expect } from '@/base/BaseTest';

function resolveDocsBaseUrl(baseURL: string | undefined): string | null {
  const explicitDocsBaseUrl = process.env.E2E_DOCS_BASE_URL?.trim();
  if (explicitDocsBaseUrl) {
    return explicitDocsBaseUrl;
  }

  if (!baseURL) {
    return null;
  }

  // The default E2E target is the console app (`/console/`), which does not host docs pages.
  if (baseURL.includes('/console/')) {
    return null;
  }

  return baseURL;
}

function toDocsUrl(docsBaseUrl: string, pathname: string): string {
  return new URL(pathname, docsBaseUrl).toString();
}

test.describe('Docs CLI Reference Link UX', () => {
  test('opens CLI reference in modal on normal click and keeps native new-tab behavior @docs @regression', async ({
    page,
    context,
    baseURL,
  }) => {
    const docsBaseUrl = resolveDocsBaseUrl(baseURL);
    if (!docsBaseUrl) {
      test.skip(
        true,
        'Docs reference tests require E2E_DOCS_BASE_URL when E2E_BASE_URL points to /console/.'
      );
      return;
    }

    await page.goto(toDocsUrl(docsBaseUrl, '/en/docs/setup'), { waitUntil: 'domcontentloaded' });

    const referenceLink = page.locator('a[data-cli-ref-link="true"]').first();
    await expect(referenceLink).toBeVisible({ timeout: 10000 });

    const href = await referenceLink.getAttribute('href');
    expect(href).toBeTruthy();

    // Same-tab click should open the in-page modal.
    await referenceLink.click();

    const modal = page.locator('[data-cli-ref-modal]');
    await expect(modal).toHaveClass(/is-open/);

    const frame = page.locator('[data-cli-ref-frame]');
    const frameSrc = await frame.getAttribute('src');
    expect(frameSrc).toContain(href as string);

    const openInNewTab = page.locator('[data-cli-ref-open-tab]');
    await expect(openInNewTab).toHaveAttribute(
      'href',
      new RegExp(String(href).replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    );

    await page.locator('.cli-ref-modal-close').click();
    await expect(modal).toBeHidden();

    // Middle click should preserve native browser behavior (new tab, no modal interception).
    const popupPromise = context.waitForEvent('page');
    await referenceLink.click({ button: 'middle' });
    const popup = await popupPromise;
    await popup.waitForLoadState('domcontentloaded');

    expect(popup.url()).toContain('/en/docs/cli-application');
    expect(popup.url()).toMatch(/#cli-(local|cloud)-/);

    await popup.close();
  });

  test('opens terminal disclaimer CLI reference in modal and preserves middle-click new tab @docs @regression', async ({
    page,
    context,
    baseURL,
  }) => {
    const docsBaseUrl = resolveDocsBaseUrl(baseURL);
    if (!docsBaseUrl) {
      test.skip(
        true,
        'Docs reference tests require E2E_DOCS_BASE_URL when E2E_BASE_URL points to /console/.'
      );
      return;
    }

    await page.goto(toDocsUrl(docsBaseUrl, '/en/for-devops'), { waitUntil: 'domcontentloaded' });

    const referenceLink = page
      .locator('.sp-terminal-disclaimer a[data-cli-ref-link="true"]')
      .first();
    await expect(referenceLink).toBeVisible({ timeout: 10000 });
    await expect(referenceLink).toContainText('rdc ');

    const href = await referenceLink.getAttribute('href');
    expect(href).toBeTruthy();

    await referenceLink.click();

    const modal = page.locator('[data-cli-ref-modal]');
    await expect(modal).toHaveClass(/is-open/);

    const frame = page.locator('[data-cli-ref-frame]');
    const frameSrc = await frame.getAttribute('src');
    expect(frameSrc).toContain(href as string);

    await page.locator('.cli-ref-modal-close').click();
    await expect(modal).toBeHidden();

    const popupPromise = context.waitForEvent('page');
    await referenceLink.click({ button: 'middle' });
    const popup = await popupPromise;
    await popup.waitForLoadState('domcontentloaded');

    expect(popup.url()).toContain('/en/docs/cli-application');
    expect(popup.url()).toMatch(/#cli-(local|cloud)-/);

    await popup.close();
  });
});
