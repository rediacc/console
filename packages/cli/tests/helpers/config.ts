import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { DEFAULT_TEST_API_URL, DEFAULT_TEST_TIMEOUT } from './constants.js';
import type { TestAccount } from './registration.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export interface TestConfig {
  apiUrl: string;
  email: string;
  password: string;
  cliDir: string;
  timeout: number;
}

// Re-export TestAccount from registration.ts (single source of truth)
export type { TestAccount } from './registration.js';

let config: TestConfig | null = null;
let currentTestAccount: TestAccount | null = null;

export function getConfig(): TestConfig {
  if (config) return config;

  // Use dynamically registered test account if available
  const email = currentTestAccount?.email ?? process.env.REDIACC_TEST_EMAIL ?? '';
  const password = currentTestAccount?.password ?? process.env.REDIACC_TEST_PASSWORD ?? '';

  config = {
    apiUrl: process.env.REDIACC_TEST_API_URL ?? DEFAULT_TEST_API_URL,
    email,
    password,
    cliDir: resolve(__dirname, '../..'),
    timeout: parseInt(process.env.REDIACC_TEST_TIMEOUT ?? String(DEFAULT_TEST_TIMEOUT), 10),
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
  testContextName = null;
}

// Test context name for isolation during parallel test execution
let testContextName: string | null = null;

/**
 * Set the test context name (used by setup.ts).
 * The context will be passed via --context flag to CLI commands.
 */
export function setTestContextName(name: string | null): void {
  testContextName = name;
}

/**
 * Get the current test context name.
 * Returns null if no test context is set.
 */
export function getTestContextName(): string | null {
  return testContextName;
}
