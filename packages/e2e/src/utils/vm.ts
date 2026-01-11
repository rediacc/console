import { test } from '@playwright/test';

/**
 * VM Infrastructure Availability
 *
 * Set VM_DEPLOYMENT=true to enable VM-dependent tests.
 * When VMs are not available, these tests will be skipped.
 */
const VM_ENABLED = process.env.VM_DEPLOYMENT === 'true';

/**
 * Skip the current test if VM infrastructure is not available.
 *
 * Usage in test files:
 * ```typescript
 * import { skipIfNoVm } from '@/utils/vm';
 *
 * test.describe('Machine Operations', () => {
 *   test.beforeEach(() => {
 *     skipIfNoVm();
 *   });
 *
 *   test('should create machine', async ({ page }) => {
 *     // This test will be skipped if VM_DEPLOYMENT !== 'true'
 *   });
 * });
 * ```
 */
export function skipIfNoVm(): void {
  test.skip(!VM_ENABLED, 'VM infrastructure not available - set VM_DEPLOYMENT=true to enable');
}
