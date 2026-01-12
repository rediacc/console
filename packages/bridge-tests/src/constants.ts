/**
 * E2E Test Constants
 *
 * Centralized configuration values used across bridge tests.
 * These should match the system configuration in .env and organization vault.
 */

import { TEST_ENV } from './config/testEnv';

/**
 * Default datastore path used for machine setup and repository operations.
 * Matches REDIACC_DEV_MACHINES datastore path in .env
 */
// eslint-disable-next-line no-restricted-syntax -- Re-exporting TEST_ENV properties as named constants for clarity
export const DEFAULT_DATASTORE_PATH = TEST_ENV.datastorePath;
export const DEFAULT_BRIDGE_IP = TEST_ENV.vm.bridgeIp;
export const DEFAULT_WORKER_1_IP = TEST_ENV.vm.worker1Ip;
export const DEFAULT_WORKER_2_IP = TEST_ENV.vm.worker2Ip;
export const DEFAULT_RUSTFS_ENDPOINT = TEST_ENV.rustfs.endpoint;
export const DEFAULT_RUSTFS_ACCESS_KEY = TEST_ENV.rustfs.accessKey;
export const DEFAULT_RUSTFS_SECRET_KEY = TEST_ENV.rustfs.secretKey;
export const DEFAULT_RUSTFS_BUCKET = TEST_ENV.rustfs.bucket;

/**
 * Universal user ID for rediacc system user.
 * Matches UNIVERSAL_USER_ID in organization vault and .env
 * VMs have builder:x:1000:1000 pre-existing, so we use 7111 instead.
 */
// eslint-disable-next-line no-restricted-syntax -- Re-exporting TEST_ENV properties as named constants for clarity
export const DEFAULT_UID = TEST_ENV.uid;

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
 * Docker socket path: /var/run/rediacc/docker-{networkId}.sock
 */
export const FORK_NETWORK_ID_A = TEST_ENV.network.forkA;
export const FORK_NETWORK_ID_B = TEST_ENV.network.forkB;

/**
 * Test-specific constants
 */
// eslint-disable-next-line no-restricted-syntax -- Re-exporting TEST_ENV properties as named constants for clarity
export const TEST_REPOSITORY_NAME = TEST_ENV.testRepositoryName;
// eslint-disable-next-line no-restricted-syntax -- Re-exporting TEST_ENV properties as named constants for clarity
export const TEST_CONTAINER_PREFIX = TEST_ENV.testContainerPrefix;
// eslint-disable-next-line no-restricted-syntax -- Re-exporting TEST_ENV properties as named constants for clarity
export const TEST_PASSWORD = TEST_ENV.testPassword;
// eslint-disable-next-line no-restricted-syntax -- Re-exporting TEST_ENV properties as named constants for clarity
export const TEST_USER = TEST_ENV.testUser;
// eslint-disable-next-line no-restricted-syntax -- Re-exporting TEST_ENV properties as named constants for clarity
export const TEST_TEAM = TEST_ENV.testTeam;

/**
 * Renet binary installation path.
 * NOTE: Mirrored from renet/pkg/common/constants.go (RenetBinaryPath)
 *
 * Uses /usr/bin because sudo's restricted PATH doesn't include /usr/local/bin.
 */
// eslint-disable-next-line no-restricted-syntax -- Re-exporting TEST_ENV properties as named constants for clarity
export const RENET_BINARY_PATH = TEST_ENV.renetBinaryPath;

/**
 * Ceph health wait settings for bridge tests.
 */
export const CEPH_HEALTH_TIMEOUT_MS = 1200000;
export const CEPH_HEALTH_RETRY_MS = 15000;
