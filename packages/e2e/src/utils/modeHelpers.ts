import { Page } from '@playwright/test';

/**
 * Switches to expert mode by navigating through the user menu
 * and selecting the Expert radio option.
 */
export async function switchToExpertMode(page: Page): Promise<void> {
  await page.getByTestId('user-menu-button').click();
  await page.getByTestId('main-mode-toggle').click();
  await page.getByRole('radio', { name: 'safety-certificate Expert' }).nth(1).click();
}
