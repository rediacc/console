import { chromium, FullConfig } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { requireEnvVar } from '../utils/env';

async function globalSetup(config: FullConfig) {
  console.log('🚀 Starting global setup...');

  createDirectories();
  
  await setupAuthentication();

  console.log('✅ Global setup completed');
}

function createDirectories() {
  const dirs = ['screenshots', 'reports', 'test-results', 'reports/html-report'];
  
  dirs.forEach(dir => {
    const fullPath = path.resolve(dir);
    if (!fs.existsSync(fullPath)) {
      fs.mkdirSync(fullPath, { recursive: true });
      console.log(`📁 Created directory: ${dir}`);
    }
  });
}

async function setupAuthentication() {
  console.log('🔐 Setting up authentication...');
  
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
        password: requireEnvVar('TEST_USER_PASSWORD')
      };

      await page.fill('[data-testid="login-email-input"]', loginData.email);
      await page.fill('[data-testid="login-password-input"]', loginData.password);
      await page.click('[data-testid="login-submit-button"]');
      
      try {
        await page.waitForURL(`${baseURL}/console/**`, { timeout: 10000 });
        console.log('✅ Authentication setup successful');
        
        await page.context().storageState({ path: 'auth.json' });
      } catch (error) {
        console.log('⚠️ Authentication setup skipped - login page not accessible or credentials invalid');
      }
    } else {
      console.log('⚠️ Login page not found - authentication setup skipped');
    }
  } catch (error) {
    console.log(`⚠️ Authentication setup failed: ${error}`);
  } finally {
    await context.close();
    await browser.close();
  }
}

export default globalSetup;