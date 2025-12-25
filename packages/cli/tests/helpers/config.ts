import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export interface TestConfig {
  apiUrl: string;
  email: string;
  password: string;
  cliDir: string;
  timeout: number;
}

export interface TestAccount {
  companyName: string;
  email: string;
  password: string;
}

let config: TestConfig | null = null;
let currentTestAccount: TestAccount | null = null;

export function getConfig(): TestConfig {
  if (config) return config;

  // Use dynamically registered test account if available
  const email = currentTestAccount?.email ?? process.env.REDIACC_TEST_EMAIL ?? '';
  const password = currentTestAccount?.password ?? process.env.REDIACC_TEST_PASSWORD ?? '';

  config = {
    apiUrl:
      process.env.REDIACC_TEST_API_URL ?? 'https://retained-patricia-hawk-int.trycloudflare.com',
    email,
    password,
    cliDir: resolve(__dirname, '../..'),
    timeout: parseInt(process.env.REDIACC_TEST_TIMEOUT ?? '30000', 10),
  };

  return config;
}

/**
 * Set the test account for this test run
 * Called after fresh registration
 */
export function setTestAccount(account: TestAccount): void {
  currentTestAccount = account;
  // Reset config so it picks up new credentials
  config = null;
}

/**
 * Get the current test account
 */
export function getTestAccount(): TestAccount | null {
  return currentTestAccount;
}

export function resetConfig(): void {
  config = null;
  currentTestAccount = null;
}
