import { expect, type Page } from '@playwright/test';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';

export async function createTeamViaUI(page: Page, teamName: string): Promise<void> {
  const nav = new NavigationHelper(page);
  await nav.goToOrganizationTeams();

  const createButton = page.getByTestId(TeamPageIDS.systemCreateTeamButton);
  await expect(createButton).toBeVisible({ timeout: 5000 });
  await createButton.click();

  const teamNameInput = page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput);
  await expect(teamNameInput).toBeVisible({ timeout: 5000 });
  await teamNameInput.click();
  await teamNameInput.fill(teamName);

  await page.getByTestId(TeamPageIDS.vaultEditorGenerateSshPrivateKey).click();
  await page.getByTestId(TeamPageIDS.vaultEditorGenerateButton).click();
  await page.getByTestId(TeamPageIDS.vaultEditorApplyGenerated).click();
  await page.getByTestId(TeamPageIDS.resourceModalOkButton).click();

  await expect(page.getByTestId(`resource-list-item-${teamName}`)).toBeVisible({
    timeout: 10000,
  });
}
