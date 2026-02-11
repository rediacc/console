import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';
import { UserPageIDs } from '@/pages/user/UserPageIDs';
import { createUserViaUI } from '@/test-helpers/user-helpers';

test.describe('User Permission Tests - Deactivate', () => {
    let dashboardPage: DashboardPage;
    let loginPage: LoginPage;

    test.beforeEach(async ({ page }) => {
        loginPage = new LoginPage(page);
        dashboardPage = new DashboardPage(page);

        await loginPage.navigate();
        await loginPage.performQuickLogin();
        await dashboardPage.waitForNetworkIdle();
    });

    test('should deactivate user @system @users @permissions @regression', async ({
        page,
        testReporter,
        testDataManager,
    }) => {
        const dismissDrawerMask = async (): Promise<void> => {
            const mask = page.locator('.ant-drawer-mask');
            if (await mask.isVisible().catch(() => false)) {
                try {
                    await mask.click({ force: true });
                    await mask.waitFor({ state: 'hidden', timeout: 3000 });
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
        };
        const waitForNoModal = async (): Promise<void> => {
            const modalWrap = page.locator('.ant-modal-wrap');
            if (await modalWrap.isVisible().catch(() => false)) {
                const closeButton = modalWrap.getByRole('button', { name: /close/i }).first();
                if (await closeButton.isVisible().catch(() => false)) {
                    await closeButton.click();
                } else {
                    await page.keyboard.press('Escape').catch(() => null);
                }
            }
            await expect(modalWrap).toBeHidden({ timeout: 5000 });
        };
        const filterUsersList = async (email: string): Promise<void> => {
            const searchInput = page.getByTestId('resource-list-search');
            if (await searchInput.isVisible().catch(() => false)) {
                await searchInput.fill('');
                await searchInput.fill(email);
                await searchInput.press('Enter');
            }
        };
        const clickListAction = async (email: string, action: 'activate' | 'deactivate') => {
            const listItem = page.getByTestId(UserPageIDs.resourceListItem(email));
            await expect(listItem).toBeVisible();
            const actionsButton = listItem.getByRole('button', { name: /actions/i });
            await expect(actionsButton).toBeVisible();
            await dismissDrawerMask();
            await actionsButton.click();
            const menuItem = page.getByRole('menuitem', {
                name: action === 'activate' ? /activate/i : /deactivate/i,
            });
            await menuItem.waitFor({ state: 'visible', timeout: 3000 });
            await menuItem.click();
        };
        const confirmYes = async (): Promise<void> => {
            const confirmButton = page.getByRole('button', { name: /yes/i });
            await expect(confirmButton).toBeVisible();
            await confirmButton.click();
            await waitForNoModal();
        };

        const createdUser = await createUserViaUI(page, testDataManager);
        const newUserEmail = createdUser.email;

        testReporter.startStep('Navigate to Users section');

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
        await filterUsersList(newUserEmail);
        testReporter.completeStep('Navigate to Users section', 'passed');

        testReporter.startStep('Deactivate user');
        const isTableLayout = await userTable.isVisible().catch(() => false);
        if (isTableLayout) {
            const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(newUserEmail));
            const deactivateButton = page.getByTestId(
                UserPageIDs.systemUserDeactivateButton(newUserEmail)
            );
            if (await activateButton.isVisible().catch(() => false)) {
                await waitForNoModal();
                await activateButton.click();
                await confirmYes();
            }
            await expect(deactivateButton).toBeVisible({ timeout: 5000 });
            await waitForNoModal();
            await deactivateButton.click();
            await confirmYes();
            await expect(activateButton).toBeVisible({ timeout: 5000 });
        } else {
            const listItem = page.getByTestId(UserPageIDs.resourceListItem(newUserEmail));
            await expect(listItem).toBeVisible({ timeout: 5000 });
            const activeTag = listItem.getByText('Active', { exact: true });
            const inactiveTag = listItem.getByText('Inactive', { exact: true });
            if (await inactiveTag.isVisible().catch(() => false)) {
                await clickListAction(newUserEmail, 'activate');
                await expect(activeTag).toBeVisible();
            }
            await clickListAction(newUserEmail, 'deactivate');
            await expect(inactiveTag).toBeVisible();
        }

        await testDataManager.updateCreatedUserActivation(newUserEmail, false);
        testReporter.completeStep('Deactivate user', 'passed');
        await testReporter.finalizeTest();
    });
});
