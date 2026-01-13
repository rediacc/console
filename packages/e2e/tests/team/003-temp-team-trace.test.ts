import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { test, expect } from '../../src/base/BaseTest';
import { E2E_DEFAULTS } from '../../src/utils/constants';
import { createTeamViaUI } from '../helpers/team-helpers';

test.describe('Team Trace Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should trace team audit records @system @organization @audit @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    const teamName = `e2e-team-${Date.now()}`;

    testReporter.startStep('Trace team audit records');

    await createTeamViaUI(page, teamName);
    await page.getByTestId(TeamPageIDS.systemTeamTraceButton(teamName)).click();
    const auditRecordsText = await page
      .getByTestId(TeamPageIDS.auditTraceTotalRecords)
      .locator('strong')
      .textContent();
    const recordCount = Number.parseInt(auditRecordsText ?? E2E_DEFAULTS.CPU_COUNT_STRING);
    expect(recordCount).toBeGreaterThan(0);
    await page.getByRole('button', { name: 'Close' }).click();

    testReporter.completeStep('Trace team audit records', 'passed');

    await testReporter.finalizeTest();
  });
});
