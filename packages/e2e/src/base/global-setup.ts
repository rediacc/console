import fs from 'node:fs';
import path from 'node:path';
import { chromium, FullConfig } from '@playwright/test';
import { requireEnvVar } from '../utils/env';

async function globalSetup(_config: FullConfig) {
  console.warn('Starting global setup...');

  createDirectories();

  await setupAuthentication();

  console.warn('Global setup completed');
}

function createDirectories() {
  const dirs = ['screenshots', 'reports', 'test-results', 'reports/html-report'];

  for (const dir of dirs) {
    const fullPath = path.resolve(dir);
    if (!fs.existsSync(fullPath)) {
      fs.mkdirSync(fullPath, { recursive: true });
      console.warn(`Created directory: ${dir}`);
    }
  }
}

async function setupAuthentication() {
  console.warn('Setting up authentication...');

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    const baseURL = requireEnvVar('BASE_URL');

    await page.goto(`${baseURL}/console/login`);

    const emailInput = page.locator('[data-testid="login-email-input"]');
    if (await emailInput.isVisible({ timeout: 5000 })) {
      const loginData = {
        email: requireEnvVar('TEST_USER_EMAIL'),
        password: requireEnvVar('TEST_USER_PASSWORD'),
      };

      await page.fill('[data-testid="login-email-input"]', loginData.email);
      await page.fill('[data-testid="login-password-input"]', loginData.password);
      await page.click('[data-testid="login-submit-button"]');

      try {
        await page.waitForURL(`${baseURL}/console/**`, { timeout: 10000 });
        console.warn('Authentication setup successful');

        await page.context().storageState({ path: 'auth.json' });
      } catch {
        console.warn(
          'Authentication setup skipped - login page not accessible or credentials invalid'
        );
      }
    } else {
      console.warn('Login page not found - authentication setup skipped');
    }
  } catch (setupError) {
    console.warn(`Authentication setup failed: ${setupError}`);
  } finally {
    await context.close();
    await browser.close();
  }
}

export default globalSetup;
