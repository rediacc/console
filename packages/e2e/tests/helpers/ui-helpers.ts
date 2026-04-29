import { expect, type Page } from '@playwright/test';
import { UserPageIDs } from '@/pages/user/UserPageIDs';

export const dismissDrawerMask = async (page: Page): Promise<void> => {
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

export const waitForNoModal = async (page: Page): Promise<void> => {
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

export const filterUsersList = async (page: Page, email: string): Promise<void> => {
  const searchInput = page.getByTestId('resource-list-search');
  if (await searchInput.isVisible().catch(() => false)) {
    await searchInput.fill('');
    await searchInput.fill(email);
    await searchInput.press('Enter');
    // Wait for search results to update
    await page.waitForLoadState('networkidle').catch(() => {});
  }
};

export const clickListAction = async (
  page: Page,
  email: string,
  action: 'activate' | 'deactivate'
): Promise<void> => {
  const listItem = page.getByTestId(UserPageIDs.resourceListItem(email));
  await expect(listItem).toBeVisible();
  const actionsButton = listItem.getByRole('button', { name: /actions/i });
  await expect(actionsButton).toBeVisible();
  await dismissDrawerMask(page);
  await actionsButton.click();
  const menuItem = page.getByRole('menuitem', {
    name: action === 'activate' ? /activate/i : /deactivate/i,
  });
  await menuItem.waitFor({ state: 'visible', timeout: 3000 });
  await menuItem.click();
};

export const confirmYes = async (page: Page): Promise<void> => {
  const confirmButton = page.getByRole('button', { name: /yes/i });
  await expect(confirmButton).toBeVisible();
  await confirmButton.click({ force: true });
  await waitForNoModal(page);
};
