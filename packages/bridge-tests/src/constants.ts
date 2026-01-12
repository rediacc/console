/**
 * E2E Test Constants
 *
 * Centralized configuration values used across bridge tests.
 * These should match the system configuration in .env and organization vault.
 */

import { TEST_ENV } from "./config/testEnv";

/**
 * Default datastore path used for machine setup and repository operations.
 * Matches REDIACC_DEV_MACHINES datastore path in .env
 */
export const DEFAULT_DATASTORE_PATH: string = TEST_ENV.datastorePath;
export const DEFAULT_BRIDGE_IP: string = TEST_ENV.vm.bridgeIp;
export const DEFAULT_WORKER_1_IP: string = TEST_ENV.vm.worker1Ip;
export const DEFAULT_WORKER_2_IP: string = TEST_ENV.vm.worker2Ip;
export const DEFAULT_RUSTFS_ENDPOINT: string = TEST_ENV.rustfs.endpoint;
export const DEFAULT_RUSTFS_ACCESS_KEY: string = TEST_ENV.rustfs.accessKey;
export const DEFAULT_RUSTFS_SECRET_KEY: string = TEST_ENV.rustfs.secretKey;
export const DEFAULT_RUSTFS_BUCKET: string = TEST_ENV.rustfs.bucket;

/**
 * Universal user ID for rediacc system user.
 * Matches UNIVERSAL_USER_ID in organization vault and .env
 * VMs have builder:x:1000:1000 pre-existing, so we use 7111 instead.
 */
export const DEFAULT_UID: string = TEST_ENV.uid;

/**
 * Default network ID for test environments.
 * Used by daemon operations that require network context.
 *
 * Network ID formula: 2816 + (n * 64)
 * - 9152 = 2816 + (99 * 64)  - Default/Parent
 * - 9216 = 2816 + (100 * 64) - Fork A
 * - 9280 = 2816 + (101 * 64) - Fork B
 */
export const DEFAULT_NETWORK_ID: string = TEST_ENV.network.defaultId;

/**
 * Default Ceph PG count for test pools.
 * Keeps small clusters within pg-per-osd limits.
 */
export const DEFAULT_CEPH_POOL_PG_NUM: string = TEST_ENV.network.defaultCephPgNum;

/**
 * Fork network IDs for repository isolation tests.
 * Each fork needs its own network ID to have isolated Docker daemon.
 * Docker socket path: /var/run/rediacc/docker-{networkId}.sock
 */
export const FORK_NETWORK_ID_A: string = TEST_ENV.network.forkA;
export const FORK_NETWORK_ID_B: string = TEST_ENV.network.forkB;

/**
 * Test-specific constants
 */
export const TEST_REPOSITORY_PREFIX: string = TEST_ENV.testRepositoryPrefix;
export const TEST_REPOSITORY_NAME: string = TEST_ENV.testRepositoryName;
export const TEST_CONTAINER_PREFIX: string = TEST_ENV.testContainerPrefix;
export const TEST_PASSWORD: string = TEST_ENV.testPassword;
export const TEST_USER: string = TEST_ENV.testUser;
export const TEST_TEAM: string = TEST_ENV.testTeam;

/**
 * Renet binary installation path.
 * NOTE: Mirrored from renet/pkg/common/constants.go (RenetBinaryPath)
 *
 * Uses /usr/bin because sudo's restricted PATH doesn't include /usr/local/bin.
 */
export const RENET_BINARY_PATH: string = TEST_ENV.renetBinaryPath;

/**
 * Ceph health wait settings for bridge tests.
 */
export const CEPH_HEALTH_TIMEOUT_MS: number = 1200000;
export const CEPH_HEALTH_RETRY_MS: number = 15000;
