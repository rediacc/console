import * as fs from 'node:fs';
import * as path from 'node:path';

export interface E2EGlobalState {
  email: string;
  password: string;
  organizationName: string;
  createdAt: string;
}

const STATE_FILE = path.resolve(__dirname, '../../.e2e-state.json');

export function saveGlobalState(state: E2EGlobalState): void {
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

export function loadGlobalState(): E2EGlobalState {
  if (!fs.existsSync(STATE_FILE)) {
    throw new Error('E2E state not found. Global setup may have failed.');
  }
  return JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
}

export function cleanupGlobalState(): void {
  if (fs.existsSync(STATE_FILE)) {
    fs.unlinkSync(STATE_FILE);
  }
}
