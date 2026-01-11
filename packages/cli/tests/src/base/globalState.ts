import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Global state shared between setup and tests.
 * This file-based approach is required because Playwright's global setup
 * runs in a separate process from test workers.
 */
export interface GlobalTestState {
  contextName: string;
  email: string;
  password: string;
  /** Master password for vault encryption (separate from login password) */
  masterPassword: string;
  apiUrl: string;
}

const STATE_FILE = path.resolve(__dirname, '../../.test-state.json');

/**
 * Save global state to file (called from global setup).
 */
export function saveGlobalState(state: GlobalTestState): void {
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

/**
 * Load global state from file (called from tests).
 * Throws if state file doesn't exist (setup failed or didn't run).
 */
export function loadGlobalState(): GlobalTestState {
  if (!fs.existsSync(STATE_FILE)) {
    throw new Error(
      'Global test state not found. Global setup may have failed or did not run.\n' +
        'Run tests with: npm test'
    );
  }
  const content = fs.readFileSync(STATE_FILE, 'utf-8');
  return JSON.parse(content) as GlobalTestState;
}

/**
 * Clean up state file (called from global teardown).
 */
export function cleanupGlobalState(): void {
  if (fs.existsSync(STATE_FILE)) {
    fs.unlinkSync(STATE_FILE);
  }
}
