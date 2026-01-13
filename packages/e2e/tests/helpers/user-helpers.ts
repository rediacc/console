import { expect, type Page } from '@playwright/test';
import { LoginPage } from '../../pages/auth/LoginPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { loadGlobalState } from '../../src/setup/global-state';
import { TestDataManager, type CreatedUser } from '../../src/utils/data/TestDataManager';

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
    await nav.goToOrganizationUsers();
    const searchInput = page.getByTestId('resource-list-search');
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill(email);
      await searchInput.press('Enter');
    }
    await expect(page.getByTestId(UserPageIDs.resourceListItem(email))).toBeVisible({ timeout });
  };

  try {
    await verifyCreatedUserVisible(10000);
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
    await verifyCreatedUserVisible(10000);
  }

  testDataManager.addCreatedUser(email, password, false);
  return testDataManager.getCreatedUser(email);
}

export async function ensureCreatedUser(
  page: Page,
  testDataManager: TestDataManager
): Promise<CreatedUser> {
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

  return await attemptCreate();
}
