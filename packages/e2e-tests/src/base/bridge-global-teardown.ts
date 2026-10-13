import { FullConfig } from '@playwright/test';
import { log } from '../utils/log';

/**
 * Global teardown for bridge tests.
 *
 * In local mode, there's nothing to clean up - renet runs directly.
 */
function bridgeGlobalTeardown(_config: FullConfig) {
  log('');
  log('='.repeat(60));
  log('Bridge Test Teardown');
  log('='.repeat(60));
  log('');
}

export default bridgeGlobalTeardown;
