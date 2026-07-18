import { FullConfig } from '@playwright/test';

/**
 * Global teardown for bridge tests.
 *
 * In local mode, there's nothing to clean up - renet runs directly.
 */
function bridgeGlobalTeardown(_config: FullConfig) {
  /* eslint-disable no-console */
  console.log('');
  console.log('='.repeat(60));
  console.log('Bridge Test Teardown');
  console.log('='.repeat(60));
  console.log('');
  /* eslint-enable no-console */
}

export default bridgeGlobalTeardown;
