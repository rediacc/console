import { expect, type Page } from '@playwright/test';
import { LoginPage } from '../../pages/auth/LoginPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { loadGlobalState } from '../../src/setup/global-state';
import { TestDataManager, type CreatedUser } from '../../src/utils/data/TestDataManager';

async function getExistingSecondaryUser(
  page: Page,
  testDataManager: TestDataManager
): Promise<CreatedUser> {
  const state = loadGlobalState();
  const nav = new NavigationHelper(page);
  await nav.goToOrganizationUsers();

  const rows = page
    .getByTestId(UserPageIDs.systemUserTable)
    .locator('tbody tr:not(.ant-table-measure-row)');
  await expect(rows.first()).toBeVisible({ timeout: 10000 });
  const rowCount = await rows.count();

  for (let i = 0; i < rowCount; i++) {
    const row = rows.nth(i);
    const email = (await row.locator('strong').first().innerText()).trim();
    const rowText = (await row.innerText()).toLowerCase();
    const isBridgeUser = rowText.includes('bridges') || email.startsWith('bridge.');
    if (email && email !== state.email && !isBridgeUser) {
      const existing: CreatedUser = {
        email,
        password: '',
        createdAt: new Date().toISOString(),
        activated: true,
      };
      testDataManager.addCreatedUser(email, '');
      return existing;
    }
  }

  throw new Error('No secondary user found in user list');
}

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
  await expect(userTable).toBeVisible({ timeout: 10000 });

  const createUserButton = page.getByTestId(UserPageIDs.systemCreateUserButton);
  await expect(createUserButton).toBeVisible({ timeout: 5000 });
  await createUserButton.click();

  const emailField = page.getByTestId(UserPageIDs.resourceFormFieldEmail);
  const passwordField = page.getByTestId(UserPageIDs.resourceFormFieldPassword);
  await expect(emailField).toBeVisible();
  await expect(passwordField).toBeVisible();

  await emailField.fill(email);
  await passwordField.fill(password);

  const submitButton = page.getByTestId(UserPageIDs.resourceFormSubmitButton);
  await expect(submitButton).toBeVisible();
  await submitButton.click();
  const createModal = page.getByTestId('users-create-modal');
  await expect(createModal).toBeHidden({ timeout: 10000 });

  await page.reload();
  await page.waitForLoadState('networkidle');
  const loginEmail = page.getByTestId('login-email-input');
  if (await loginEmail.isVisible().catch(() => false)) {
    const loginPage = new LoginPage(page);
    const state = loadGlobalState();
    await loginPage.login(state.email, state.password);
    await loginPage.waitForLoginCompletion();
  }
  await nav.goToOrganizationUsers();

  try {
    const searchInput = page.getByTestId('resource-list-search');
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill(email);
      await searchInput.press('Enter');
    }
    await expect(page.getByTestId(UserPageIDs.resourceListItem(email))).toBeVisible({
      timeout: 20000,
    });
  } catch {
    console.warn(`[E2E] Created user not visible, falling back to existing user`);
    return getExistingSecondaryUser(page, testDataManager);
  }

  testDataManager.addCreatedUser(email, password, false);
  return testDataManager.getCreatedUser(email);
}

export async function ensureCreatedUser(
  page: Page,
  testDataManager: TestDataManager
): Promise<CreatedUser> {
  try {
    const existing = testDataManager.getCreatedUser();
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();
    const searchInput = page.getByTestId('resource-list-search');
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill(existing.email);
      await searchInput.press('Enter');
    }
    const existingRow = page.getByTestId(UserPageIDs.resourceListItem(existing.email));
    if (await existingRow.isVisible().catch(() => false)) {
      return existing;
    }

    testDataManager.removeCreatedUser(existing.email);
  } catch {
    // Ignore and fall back to creating or selecting another user below.
  }

  try {
    return await createUserViaUI(page, testDataManager);
  } catch (error) {
    console.warn(`[E2E] Failed to create user via UI, falling back to existing user`, error);
    return getExistingSecondaryUser(page, testDataManager);
  }
}
