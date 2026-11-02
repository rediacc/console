/**
 * E2E Test Constants
 *
 * Centralized configuration values used across bridge tests.
 * These should match the system configuration in .env and organization vault.
 */

import { version as pkgVersion } from '../../../package.json';
import { TEST_ENV } from './config/testEnv';

/**
 * Top-level TEST_ENV values re-exported as named constants:
 * - DEFAULT_DATASTORE_PATH: datastore path used for machine setup and repository operations.
 *   Matches REDIACC_DEV_MACHINES datastore path in .env
 * - DEFAULT_UID: universal user ID for the rediacc system user.
 *   Matches UNIVERSAL_USER_ID in organization vault and .env
 *   VMs have builder:x:1000:1000 pre-existing, so 7111 is used instead.
 * - TEST_REPOSITORY_NAME, TEST_PASSWORD, TEST_USER, TEST_TEAM: test-specific values.
 */
export const {
  datastorePath: DEFAULT_DATASTORE_PATH,
  uid: DEFAULT_UID,
  testRepositoryName: TEST_REPOSITORY_NAME,
  testPassword: TEST_PASSWORD,
  testUser: TEST_USER,
  testTeam: TEST_TEAM,
} = TEST_ENV;

export const DEFAULT_BRIDGE_IP = TEST_ENV.vm.bridgeIp;
export const DEFAULT_WORKER_1_IP = TEST_ENV.vm.worker1Ip;
export const DEFAULT_WORKER_2_IP = TEST_ENV.vm.worker2Ip;
export const DEFAULT_RUSTFS_ENDPOINT = TEST_ENV.rustfs.endpoint;
export const DEFAULT_RUSTFS_ACCESS_KEY = TEST_ENV.rustfs.accessKey;
export const DEFAULT_RUSTFS_SECRET_KEY = TEST_ENV.rustfs.secretKey;
export const DEFAULT_RUSTFS_BUCKET = TEST_ENV.rustfs.bucket;

/**
 * Default network ID for test environments.
 * Used by daemon operations that require network context.
 *
 * Network ID formula: 2816 + (n * 64)
 * - 9152 = 2816 + (99 * 64)  - Default/Parent
 * - 9216 = 2816 + (100 * 64) - Fork A
 * - 9280 = 2816 + (101 * 64) - Fork B
 */
export const DEFAULT_NETWORK_ID = TEST_ENV.network.defaultId;

/**
 * Fork network IDs for repository isolation tests.
 * Each fork needs its own network ID to have isolated Docker daemon.
 * Docker socket path: /var/run/rediacc/net-{networkId}/docker-{networkId}.sock (repoDockerSocketPath)
 */
export const FORK_NETWORK_ID_A = TEST_ENV.network.forkA;
export const FORK_NETWORK_ID_B = TEST_ENV.network.forkB;

/**
 * Installation path for renet on VMs (NOT the local build path).
 * NOTE: Mirrored from renet/pkg/common/constants.go (RenetInstallRoot)
 *
 * Reads version from root package.json to stay in sync with releases.
 */
export const VM_RENET_INSTALL_PATH = `/usr/lib/rediacc/renet/${pkgVersion}/renet`;

/**
 * Ceph health wait settings for bridge tests.
 */
export const CEPH_HEALTH_TIMEOUT_MS = 1200000;
export const CEPH_HEALTH_RETRY_MS = 15000;

/**
 * Timeout for renet setup command on VMs.
 * Installing Docker from scratch on base images takes 2-4 minutes depending on distro.
 * Set to 5 minutes to be safe across all distros (Fedora, openSUSE, Ubuntu, Debian).
 */
export const RENET_SETUP_TIMEOUT_MS = 300000;
