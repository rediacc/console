/**
 * E2E Test Constants
 *
 * Centralized configuration values used across bridge tests.
 * These should match the system configuration in .env and organization vault.
 */
/**
 * Default datastore path used for machine setup and repository operations.
 * Matches REDIACC_DEV_MACHINES datastore path in .env
 */
export declare const DEFAULT_DATASTORE_PATH: "/mnt/rediacc";
export declare const DEFAULT_BRIDGE_IP: "192.168.111.1";
export declare const DEFAULT_WORKER_1_IP: "192.168.111.11";
export declare const DEFAULT_WORKER_2_IP: "192.168.111.12";
export declare const DEFAULT_RUSTFS_ENDPOINT: "http://192.168.111.1:9000";
export declare const DEFAULT_RUSTFS_ACCESS_KEY: "rustfsadmin";
export declare const DEFAULT_RUSTFS_SECRET_KEY: "rustfsadmin";
export declare const DEFAULT_RUSTFS_BUCKET: "rediacc-test";
/**
 * Universal user ID for rediacc system user.
 * Matches UNIVERSAL_USER_ID in organization vault and .env
 * VMs have builder:x:1000:1000 pre-existing, so we use 7111 instead.
 */
export declare const DEFAULT_UID: "7111";
/**
 * Default network ID for test environments.
 * Used by daemon operations that require network context.
 *
 * Network ID formula: 2816 + (n * 64)
 * - 9152 = 2816 + (99 * 64)  - Default/Parent
 * - 9216 = 2816 + (100 * 64) - Fork A
 * - 9280 = 2816 + (101 * 64) - Fork B
 */
export declare const DEFAULT_NETWORK_ID: "9152";
/**
 * Fork network IDs for repository isolation tests.
 * Each fork needs its own network ID to have isolated Docker daemon.
 * Docker socket path: /var/run/rediacc/docker-{networkId}.sock
 */
export declare const FORK_NETWORK_ID_A: "9216";
export declare const FORK_NETWORK_ID_B: "9280";
/**
 * Test-specific constants
 */
export declare const TEST_REPOSITORY_NAME: "test-repo";
export declare const TEST_CONTAINER_PREFIX: "test-container";
export declare const TEST_PASSWORD: "test-password-123";
export declare const TEST_USER: "muhammed";
export declare const TEST_TEAM: "Test Team";
/**
 * Installation path for renet on VMs (NOT the local build path).
 * NOTE: Mirrored from renet/pkg/common/constants.go (RenetInstallRoot)
 *
 * Tests pin to the current CLI version's install slot.
 */
export declare const VM_RENET_INSTALL_PATH = "/usr/lib/rediacc/renet/0.6.0/renet";
/**
 * Ceph health wait settings for bridge tests.
 */
export declare const CEPH_HEALTH_TIMEOUT_MS = 1200000;
export declare const CEPH_HEALTH_RETRY_MS = 15000;
/**
 * Timeout for renet setup command on VMs.
 * Installing Docker from scratch on base images takes 2-4 minutes depending on distro.
 * Set to 5 minutes to be safe across all distros (Fedora, openSUSE, Ubuntu, Debian).
 */
export declare const RENET_SETUP_TIMEOUT_MS = 300000;
//# sourceMappingURL=constants.d.ts.map