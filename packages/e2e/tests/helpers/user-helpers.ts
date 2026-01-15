import { expect, type Page } from '@playwright/test';
import { LoginPage } from '../../pages/auth/LoginPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { loadGlobalState } from '../../src/setup/global-state';
import { TestDataManager, type CreatedUser } from '../../src/utils/data/TestDataManager';

/* eslint-disable sonarjs/cognitive-complexity -- Complex user creation flow with multiple fallback strategies */
export async function createUserViaUI(
  page: Page,
  testDataManager: TestDataManager,
  options?: { email?: string; password?: string }
): Promise<CreatedUser> {
  const timestamp = Date.now();
  const email = options?.email ?? `e2e-user-${timestamp}@rediacc.local`;
  const password = options?.password ?? `TestPass${timestamp}!`;

  const nav = new NavigationHelper(page);
  await nav.goToOrganizationUsers();

  const userTable = page.getByTestId(UserPageIDs.systemUserTable);
  const listContainer = page.getByTestId('resource-list-container');
  await expect
    .poll(
      async () =>
        (await userTable.isVisible().catch(() => false)) ||
        (await listContainer.isVisible().catch(() => false)),
      { timeout: 10000 }
    )
    .toBe(true);

  const createUserButton = page.getByTestId(UserPageIDs.systemCreateUserButton);
  await expect(createUserButton).toBeVisible({ timeout: 5000 });
  const drawerMask = page.locator('.ant-drawer-mask');
  if (await drawerMask.isVisible().catch(() => false)) {
    try {
      await drawerMask.click({ force: true });
      await drawerMask.waitFor({ state: 'hidden', timeout: 3000 });
    } catch {
      await page.keyboard.press('Escape').catch(() => null);
      await page.evaluate(() => {
        const overlay = document.querySelector<HTMLElement>('.ant-drawer-mask');
        if (overlay) {
          overlay.style.pointerEvents = 'none';
          overlay.style.opacity = '0';
        }
      });
    }
  }
  await createUserButton.click();

  const emailField = page.getByTestId(UserPageIDs.resourceFormFieldEmail);
  const passwordField = page.getByTestId(UserPageIDs.resourceFormFieldPassword);
  await expect(emailField).toBeVisible();
  await expect(passwordField).toBeVisible();

  await emailField.fill(email);
  await passwordField.fill(password);

  const submitButton = page.getByTestId(UserPageIDs.resourceFormSubmitButton);
  await expect(submitButton).toBeVisible();
  const createResponsePromise = page.waitForResponse((response) => {
    return response.url().includes('/CreateNewUser') && response.request().method() === 'POST';
  });
  await submitButton.click();
  const createResponse = await createResponsePromise;
  if (!createResponse.ok()) {
    const body = await createResponse.text().catch(() => '<unreadable>');
    throw new Error(`CreateNewUser failed: ${createResponse.status()} ${body}`);
  }
  const createModal = page.getByTestId('users-create-modal');
  await expect(createModal).toBeHidden({ timeout: 10000 });

  const verifyCreatedUserVisible = async (timeout: number): Promise<void> => {
    await expect
      .poll(
        async () => {
          const listContainer = page.getByTestId('resource-list-container');
          if (!(await listContainer.isVisible().catch(() => false))) {
            await nav.goToOrganizationUsers();
          }
          const searchInput = page.getByTestId('resource-list-search');
          if (await searchInput.isVisible().catch(() => false)) {
            await searchInput.fill('');
            await searchInput.fill(email);
            await searchInput.press('Enter');
          }
          const rowByTestId = page.getByTestId(UserPageIDs.resourceListItem(email));
          if (await rowByTestId.isVisible().catch(() => false)) {
            return true;
          }
          if (await listContainer.isVisible().catch(() => false)) {
            return await listContainer
              .getByText(email, { exact: true })
              .isVisible()
              .catch(() => false);
          }
          const userTable = page.getByTestId(UserPageIDs.systemUserTable);
          return await userTable
            .getByText(email, { exact: true })
            .isVisible()
            .catch(() => false);
        },
        { timeout }
      )
      .toBe(true);
  };

  try {
    await verifyCreatedUserVisible(20000);
  } catch {
    await page.reload();
    await page.waitForLoadState('networkidle');
    const loginEmail = page.getByTestId('login-email-input');
    if (await loginEmail.isVisible().catch(() => false)) {
      const loginPage = new LoginPage(page);
      const state = loadGlobalState();
      await loginPage.login(state.email, state.password);
      await loginPage.waitForLoginCompletion();
    }
    await verifyCreatedUserVisible(20000);
  }

  const createDialog = page.getByRole('dialog', { name: /create user/i });
  if (
    (await createModal.isVisible().catch(() => false)) ||
    (await createDialog.isVisible().catch(() => false))
  ) {
    const closeButton = createDialog.getByRole('button', { name: /cancel|close/i }).first();
    if (await closeButton.isVisible().catch(() => false)) {
      try {
        await closeButton.click();
      } catch {
        await page.keyboard.press('Escape').catch(() => null);
      }
    } else {
      await page.keyboard.press('Escape').catch(() => null);
    }
    await expect(createModal)
      .toBeHidden({ timeout: 10000 })
      .catch(() => null);
    await expect(createDialog)
      .toBeHidden({ timeout: 10000 })
      .catch(() => null);
  }

  await testDataManager.addCreatedUser(email, password, false);
  return testDataManager.getCreatedUser(email);
}

export async function ensureCreatedUser(
  page: Page,
  testDataManager: TestDataManager
): Promise<CreatedUser> {
  const nav = new NavigationHelper(page);
  const attemptCreate = async (): Promise<CreatedUser> => {
    try {
      return await createUserViaUI(page, testDataManager);
    } catch {
      await page.reload();
      await page.waitForLoadState('networkidle');
      return await createUserViaUI(page, testDataManager);
    }
  };

  try {
    const existing = testDataManager.getCreatedUser();
    await nav.goToOrganizationUsers();
    const searchInput = page.getByTestId('resource-list-search');
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill('');
      await searchInput.fill(existing.email);
      await searchInput.press('Enter');
    }
    await expect
      .poll(
        async () => {
          const listContainer = page.getByTestId('resource-list-container');
          if (!(await listContainer.isVisible().catch(() => false))) {
            await nav.goToOrganizationUsers();
          }
          const rowByTestId = page.getByTestId(UserPageIDs.resourceListItem(existing.email));
          if (await rowByTestId.isVisible().catch(() => false)) {
            return true;
          }
          if (await listContainer.isVisible().catch(() => false)) {
            return await listContainer
              .getByText(existing.email, { exact: true })
              .isVisible()
              .catch(() => false);
          }
          const userTable = page.getByTestId(UserPageIDs.systemUserTable);
          return await userTable
            .getByText(existing.email, { exact: true })
            .isVisible()
            .catch(() => false);
        },
        { timeout: 15000 }
      )
      .toBe(true);
    return existing;
  } catch {
    try {
      const existing = testDataManager.getCreatedUser();
      await testDataManager.removeCreatedUser(existing.email);
    } catch {
      // Ignore and fall back to creating or selecting another user below.
    }
  }

  return await attemptCreate();
}
