import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { ensureDrawerIsClosed } from '@/test-helpers/team-helpers';

test.describe('Queue Operations Tests - Authenticated', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.navigate();
    await loginPage.performQuickLogin();

    const nav = new NavigationHelper(page);
    await nav.goToQueue();

    await ensureDrawerIsClosed(page);
  });

  test('should display queue page layout @queue @smoke', async ({ page, testReporter }) => {
    testReporter.startStep('Verify queue page container');

    const queueContainer = page.getByTestId('queue-page-container');
    await expect(queueContainer).toBeVisible({ timeout: 10000 });

    testReporter.completeStep('Verify queue page container', 'passed');

    testReporter.startStep('Verify statistics bar');

    const statisticsBar = page.getByTestId('queue-statistics-bar');
    await expect(statisticsBar).toBeVisible({ timeout: 10000 });

    const statsTotal = page.getByTestId('queue-stats-total');
    const statsActive = page.getByTestId('queue-stats-active');
    const statsFailed = page.getByTestId('queue-stats-failed');
    const statsStale = page.getByTestId('queue-stats-stale');

    await expect(statsTotal).toBeVisible();
    await expect(statsActive).toBeVisible();
    await expect(statsFailed).toBeVisible();
    await expect(statsStale).toBeVisible();

    testReporter.completeStep('Verify statistics bar', 'passed');

    testReporter.startStep('Verify action buttons');

    const refreshButton = page.getByTestId('queue-refresh-button');
    const exportDropdown = page.getByTestId('queue-export-dropdown');

    await expect(refreshButton).toBeVisible();
    await expect(exportDropdown).toBeVisible();

    testReporter.completeStep('Verify action buttons', 'passed');

    await testReporter.finalizeTest();
  });

  test('should display queue tabs @queue @smoke', async ({ page, testReporter }) => {
    testReporter.startStep('Verify queue tabs container');

    const queueTabs = page.getByTestId('queue-tabs');
    await expect(queueTabs).toBeVisible({ timeout: 10000 });

    testReporter.completeStep('Verify queue tabs container', 'passed');

    testReporter.startStep('Verify all tab labels are visible');

    const tabActive = page.getByTestId('queue-tab-active');
    const tabCompleted = page.getByTestId('queue-tab-completed');
    const tabCancelled = page.getByTestId('queue-tab-cancelled');
    const tabFailed = page.getByTestId('queue-tab-failed');

    await expect(tabActive).toBeVisible();
    await expect(tabCompleted).toBeVisible();
    await expect(tabCancelled).toBeVisible();
    await expect(tabFailed).toBeVisible();

    testReporter.completeStep('Verify all tab labels are visible', 'passed');

    await testReporter.finalizeTest();
  });

  test('should switch between queue tabs @queue @regression', async ({ page, testReporter }) => {
    testReporter.startStep('Wait for queue page to load');

    const queueTabs = page.getByTestId('queue-tabs');
    await expect(queueTabs).toBeVisible({ timeout: 10000 });

    testReporter.completeStep('Wait for queue page to load', 'passed');

    testReporter.startStep('Switch to Completed tab');

    const tabCompleted = page.getByTestId('queue-tab-completed');
    await tabCompleted.click();

    // Verify tab is active after clicking - the ant-tabs-tab-active class is on the parent element
    const completedTabItem = queueTabs.locator('.ant-tabs-tab', { has: tabCompleted });
    await expect(completedTabItem).toHaveClass(/ant-tabs-tab-active/, { timeout: 5000 });

    testReporter.completeStep('Switch to Completed tab', 'passed');

    testReporter.startStep('Switch to Cancelled tab');

    const tabCancelled = page.getByTestId('queue-tab-cancelled');
    await tabCancelled.click();

    const cancelledTabItem = queueTabs.locator('.ant-tabs-tab', { has: tabCancelled });
    await expect(cancelledTabItem).toHaveClass(/ant-tabs-tab-active/, { timeout: 5000 });

    testReporter.completeStep('Switch to Cancelled tab', 'passed');

    testReporter.startStep('Switch to Failed tab');

    const tabFailed = page.getByTestId('queue-tab-failed');
    await tabFailed.click();

    const failedTabItem = queueTabs.locator('.ant-tabs-tab', { has: tabFailed });
    await expect(failedTabItem).toHaveClass(/ant-tabs-tab-active/, { timeout: 5000 });

    testReporter.completeStep('Switch to Failed tab', 'passed');

    testReporter.startStep('Switch back to Active tab');

    const tabActive = page.getByTestId('queue-tab-active');
    await tabActive.click();

    const activeTabItem = queueTabs.locator('.ant-tabs-tab', { has: tabActive });
    await expect(activeTabItem).toHaveClass(/ant-tabs-tab-active/, { timeout: 5000 });

    testReporter.completeStep('Switch back to Active tab', 'passed');

    await testReporter.finalizeTest();
  });

  test('should display filter panel @queue @regression', async ({ page, testReporter }) => {
    testReporter.startStep('Verify filters card is visible');

    const filtersCard = page.getByTestId('queue-filters-card');
    await expect(filtersCard).toBeVisible({ timeout: 10000 });

    testReporter.completeStep('Verify filters card is visible', 'passed');

    testReporter.startStep('Verify filter inputs are accessible');

    const filterTeam = page.getByTestId('queue-filter-team');
    const filterMachine = page.getByTestId('queue-filter-machine');
    const filterBridge = page.getByTestId('queue-filter-bridge');
    const filterStatus = page.getByTestId('queue-filter-status');
    const filterTask = page.getByTestId('queue-filter-task');
    const checkboxOnlyStale = page.getByTestId('queue-checkbox-only-stale');

    await expect(filterTeam).toBeVisible();
    await expect(filterMachine).toBeVisible();
    await expect(filterBridge).toBeVisible();
    await expect(filterStatus).toBeVisible();
    await expect(filterTask).toBeVisible();
    await expect(checkboxOnlyStale).toBeVisible();

    testReporter.completeStep('Verify filter inputs are accessible', 'passed');

    await testReporter.finalizeTest();
  });

  test('should refresh queue data @queue', async ({ page, testReporter }) => {
    testReporter.startStep('Wait for queue page to load');

    const queueContainer = page.getByTestId('queue-page-container');
    await expect(queueContainer).toBeVisible({ timeout: 10000 });

    testReporter.completeStep('Wait for queue page to load', 'passed');

    testReporter.startStep('Click refresh button');

    const refreshButton = page.getByTestId('queue-refresh-button');
    await expect(refreshButton).toBeVisible();
    await expect(refreshButton).toBeEnabled();
    await refreshButton.click();

    // After clicking refresh, the button may briefly show a loading state
    // then return to enabled state when data is fetched
    await expect(refreshButton).toBeEnabled({ timeout: 10000 });

    testReporter.completeStep('Click refresh button', 'passed');

    await testReporter.finalizeTest();
  });
});
