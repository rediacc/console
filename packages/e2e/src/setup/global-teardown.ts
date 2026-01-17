import { cleanupGlobalState } from './global-state';
import type { FullConfig } from '@playwright/test';

function globalTeardown(_config: FullConfig): void {
  console.warn('[Teardown] Cleaning up E2E state');
  cleanupGlobalState();
}

export default globalTeardown;
