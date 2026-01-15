import { expect, type Locator, type Page } from '@playwright/test';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';

const escapeRegex = (value: string): string => value.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&');

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

  const createButton = page.getByTestId(TeamPageIDS.systemCreateTeamButton);
  await expect(createButton).toBeVisible({ timeout: 5000 });
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
