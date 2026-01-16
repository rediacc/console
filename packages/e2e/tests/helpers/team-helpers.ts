import { expect, type Locator, type Page } from '@playwright/test';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';

const escapeRegex = (value: string): string => value.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Smart navigation to ensure elements are visible on mobile/tablet devices.
 * Handles sidebar/drawer navigation and element visibility.
 */
async function ensureElementVisible(page: Page, testId: string, timeout = 10000): Promise<void> {
  const element = page.getByTestId(testId);

  // First check if element is already visible
  if (await element.isVisible({ timeout: 1000 }).catch(() => false)) {
    return;
  }

  console.warn(
    `[Mobile Navigation] Element ${testId} not visible, attempting mobile navigation strategies`
  );

  // Try different strategies
  if (await tryCloseDrawer(page, element)) return;
  if (await trySidebarToggle(page, element)) return;
  if (await tryScrollIntoView(page, element)) return;

  // Debug information
  await logDebugInfo(page, testId);

  // Final check
  console.warn(`[Mobile Navigation] Final visibility check for ${testId}`);
  await expect(element).toBeVisible({ timeout });
}

async function tryCloseDrawer(page: Page, element: Locator): Promise<boolean> {
  const drawerMask = page.locator('.ant-drawer-mask');
  if (!(await drawerMask.isVisible({ timeout: 1000 }).catch(() => false))) {
    return false;
  }

  try {
    console.warn('[Mobile Navigation] Closing drawer mask');
    await drawerMask.click({ force: true });
    await waitForAnimation(page, 500);
    if (await element.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.warn('[Mobile Navigation] Element became visible after closing drawer');
      return true;
    }
  } catch {
    // Continue to next strategy
  }
  return false;
}

async function trySidebarToggle(page: Page, element: Locator): Promise<boolean> {
  const sidebarToggle = page.getByTestId('sidebar-toggle-button');
  if (!(await sidebarToggle.isVisible({ timeout: 1000 }).catch(() => false))) {
    return false;
  }

  console.warn('[Mobile Navigation] Found sidebar toggle, attempting to open');
  // Try clicking toggle up to 2 times (in case sidebar was already open)
  for (let i = 0; i < 2; i++) {
    await sidebarToggle.click();
    await waitForAnimation(page, 1000);
    if (await element.isVisible({ timeout: 2000 }).catch(() => false)) {
      console.warn(`[Mobile Navigation] Element became visible after toggle click ${i + 1}`);
      return true;
    }
  }
  return false;
}

async function tryScrollIntoView(page: Page, element: Locator): Promise<boolean> {
  try {
    console.warn('[Mobile Navigation] Scrolling element into view');
    await element.scrollIntoViewIfNeeded();
    await waitForAnimation(page, 500);
    if (await element.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.warn('[Mobile Navigation] Element became visible after scrolling');
      return true;
    }
  } catch {
    // Continue to final check
  }
  return false;
}

async function logDebugInfo(page: Page, testId: string): Promise<void> {
  console.warn(
    `[Mobile Navigation] DEBUG: Element ${testId} still not visible after all strategies`
  );

  const elementCount = await page.getByTestId(testId).count();
  console.warn(`[Mobile Navigation] DEBUG: Element count for ${testId}: ${elementCount}`);

  const allTestIds = await page.evaluate(() => {
    const elements = document.querySelectorAll('[data-testid]');
    return Array.from(elements)
      .map((el) => el.getAttribute('data-testid'))
      .filter(Boolean);
  });
  console.warn(`[Mobile Navigation] DEBUG: All test IDs on page: ${allTestIds.join(', ')}`);

  const similarButtons = allTestIds.filter(
    (id) => id?.includes('create') || id?.includes('team') || id?.includes('button')
  );
  console.warn(`[Mobile Navigation] DEBUG: Similar buttons found: ${similarButtons.join(', ')}`);
}

async function waitForAnimation(page: Page, ms: number): Promise<void> {
  // For UI animations, we need to wait for specific durations
  // eslint-disable-next-line playwright/no-wait-for-timeout -- Animation timing requires fixed delays
  await page.waitForTimeout(ms);
}

/**
 * Ensures the mobile drawer is closed to prevent pointer event interception
 */
export async function ensureDrawerIsClosed(page: Page): Promise<void> {
  const drawer = page.locator('.ant-drawer');
  const mask = page.locator('.ant-drawer-mask');

  // Check if drawer is open
  if (await drawer.isVisible().catch(() => false)) {
    console.warn('[Mobile Navigation] Drawer still open, attempting to close');

    // Try clicking the mask first
    if (await mask.isVisible().catch(() => false)) {
      await mask.click({ force: true });
    } else {
      // Fallback: try pressing Escape or clicking outside
      await page.keyboard.press('Escape').catch(() => {});

      // Try clicking on the main content area to close drawer
      const mainContent = page.locator('main, [role="main"], .ant-layout-content').first();
      if (await mainContent.isVisible().catch(() => false)) {
        await mainContent.click({ force: true, position: { x: 100, y: 100 } }).catch(() => {});
      }
    }

    // Wait for drawer to close
    await drawer.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});

    // Additional wait for any animations
    await waitForAnimation(page, 500);

    console.warn('[Mobile Navigation] Drawer closing attempted');
  }
}

/**
 * Ensures the create team button is visible, handling mobile/tablet navigation
 * where the button might be hidden in a collapsed sidebar/menu.
 */
async function ensureCreateButtonVisible(page: Page): Promise<void> {
  // Try desktop button first
  const desktopButton = page.getByTestId(TeamPageIDS.systemCreateTeamButton);
  const mobileEmptyButton = page.getByTestId('resource-list-create-new');
  const mobileActionsButton = page
    .getByTestId('resource-list-mobile-actions')
    .getByTestId(TeamPageIDS.systemCreateTeamButton);

  // Check if desktop button is visible
  if (await desktopButton.isVisible({ timeout: 2000 }).catch(() => false)) {
    return;
  }

  // Check if mobile empty state button is visible
  if (await mobileEmptyButton.isVisible({ timeout: 2000 }).catch(() => false)) {
    return;
  }

  // Check if mobile actions button is visible (our new mobile layout)
  if (await mobileActionsButton.isVisible({ timeout: 2000 }).catch(() => false)) {
    return;
  }

  // If neither is visible, try mobile navigation strategies for desktop button
  console.warn(
    '[Mobile Navigation] Neither desktop, mobile empty, nor mobile actions button visible, trying mobile strategies'
  );
  await ensureElementVisible(page, TeamPageIDS.systemCreateTeamButton);
}

export async function waitForTeamRow(page: Page, teamName: string): Promise<Locator> {
  const listItem = page.getByTestId(`resource-list-item-${teamName}`);
  const tableRow = page
    .getByTestId(TeamPageIDS.systemTeamTable)
    .getByRole('row', { name: new RegExp(escapeRegex(teamName)) });

  if (await listItem.isVisible().catch(() => false)) {
    return listItem;
  }

  if (await tableRow.isVisible().catch(() => false)) {
    return tableRow;
  }

  await Promise.any([
    expect(listItem).toBeVisible({ timeout: 10000 }),
    expect(tableRow).toBeVisible({ timeout: 10000 }),
  ]).catch(() => null);

  if (await listItem.isVisible().catch(() => false)) {
    return listItem;
  }

  if (await tableRow.isVisible().catch(() => false)) {
    return tableRow;
  }

  const nextPageButton = page.getByRole('listitem', { name: /next page/i }).getByRole('button');
  if (await nextPageButton.isEnabled().catch(() => false)) {
    await nextPageButton.click();
    await Promise.any([
      expect(listItem).toBeVisible({ timeout: 10000 }),
      expect(tableRow).toBeVisible({ timeout: 10000 }),
    ]);
  }

  if (await listItem.isVisible().catch(() => false)) {
    return listItem;
  }

  await expect(tableRow).toBeVisible({ timeout: 10000 });
  return tableRow;
}

export async function createTeamViaUI(page: Page, teamName: string): Promise<void> {
  const nav = new NavigationHelper(page);
  await nav.goToOrganizationTeams();

  // Wait for the page to load - check for either the create button or the list container
  await expect
    .poll(
      async () => {
        const createButtonVisible = await page
          .getByTestId(TeamPageIDS.systemCreateTeamButton)
          .isVisible()
          .catch(() => false);
        const mobileEmptyButtonVisible = await page
          .getByTestId('resource-list-create-new')
          .isVisible()
          .catch(() => false);
        const mobileActionsButtonVisible = await page
          .getByTestId('resource-list-mobile-actions')
          .getByTestId(TeamPageIDS.systemCreateTeamButton)
          .isVisible()
          .catch(() => false);
        const listContainerVisible = await page
          .getByTestId('resource-list-container')
          .isVisible()
          .catch(() => false);
        return (
          createButtonVisible ||
          mobileEmptyButtonVisible ||
          mobileActionsButtonVisible ||
          listContainerVisible
        );
      },
      { timeout: 10000 }
    )
    .toBe(true);

  // Smart navigation: ensure we can see the create button
  // On mobile/tablet, the button might be hidden in a collapsed sidebar
  await ensureCreateButtonVisible(page);

  // Ensure drawer is closed before attempting to click the button
  // The drawer mask can intercept pointer events on mobile devices
  await ensureDrawerIsClosed(page);

  // Find the first visible create button (handles both desktop and mobile layouts)
  const createButton = page.getByTestId(TeamPageIDS.systemCreateTeamButton).first();
  await createButton.click();

  const teamNameInput = page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput);
  await expect(teamNameInput).toBeVisible({ timeout: 5000 });
  await teamNameInput.click();
  await teamNameInput.fill(teamName);

  await page.getByTestId(TeamPageIDS.vaultEditorGenerateSshPrivateKey).click();
  await page.getByTestId(TeamPageIDS.vaultEditorGenerateButton).click();
  await page.getByTestId(TeamPageIDS.vaultEditorApplyGenerated).click();
  await page.getByTestId(TeamPageIDS.resourceModalOkButton).click();

  const searchInput = page.getByTestId('resource-list-search');
  if (await searchInput.isVisible().catch(() => false)) {
    await searchInput.fill(teamName);
    await searchInput.press('Enter');
  }

  const resourceModal = page.getByTestId(TeamPageIDS.resourceModal);
  await expect(resourceModal)
    .toBeHidden({ timeout: 10000 })
    .catch(() => null);
  const listContainer = page.getByTestId(TeamPageIDS.resourceListContainer);
  await expect(listContainer)
    .toBeVisible({ timeout: 10000 })
    .catch(() => null);
}
