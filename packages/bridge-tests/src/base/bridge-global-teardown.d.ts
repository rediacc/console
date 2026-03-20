import { FullConfig } from '@playwright/test';
/**
 * Global teardown for bridge tests.
 *
 * In local mode, there's nothing to clean up - renet runs directly.
 */
declare function bridgeGlobalTeardown(_config: FullConfig): void;
export default bridgeGlobalTeardown;
//# sourceMappingURL=bridge-global-teardown.d.ts.map