import { MIN_NETWORK_ID } from '@rediacc/shared/queue-vault';

/**
 * Constants for local E2E test suite.
 */
export const E2E = {
  /** Prefix for E2E test context names */
  CONTEXT_PREFIX: 'e2e-local',
  /** Default test repository name (legacy — prefer per-phase names below) */
  TEST_REPO: 'test-repo-e2e',
  /** Second test repository name (for fork/backup tests) */
  TEST_REPO_2: 'test-repo-e2e-2',
  /** Per-phase repo names — eliminates cross-file name collisions */
  REPO_ADVANCED: 'test-repo-adv',
  REPO_ADVANCED_2: 'test-repo-adv-2',
  REPO_CONTAINER: 'test-repo-ctr',
  REPO_TEMPLATE: 'test-repo-tpl',
  REPO_BACKUP: 'test-repo-bak',
  /** Default datastore path on VMs */
  DATASTORE_PATH: '/mnt/rediacc',
  /** Base path for repository mount points */
  REPO_MOUNTS_BASE: '/mnt/rediacc/mounts',
  /** Base path for repository storage */
  REPO_STORAGE_BASE: '/mnt/rediacc/repositories',
  /** Machine name for VM1 in contexts */
  MACHINE_VM1: 'vm1',
  /** Machine name for VM2 in contexts */
  MACHINE_VM2: 'vm2',
  /** Default timeout per test (5 minutes) */
  TEST_TIMEOUT: 300_000,
  /** Timeout for setup operations (10 minutes) */
  SETUP_TIMEOUT: 600_000,
  /** Default repository size */
  REPO_SIZE: '4G',
  /** Expanded repository size */
  REPO_SIZE_EXPANDED: '8G',
  /** Network ID for Docker daemon isolation (base minimum, matches production) */
  NETWORK_ID: MIN_NETWORK_ID,
  /** Network ID as string for use in CLI params */
  NETWORK_ID_STR: String(MIN_NETWORK_ID),
  /** Docker compose content for container tests */
  DOCKER_COMPOSE_CONTENT: `version: '3'
services:
  web:
    image: nginx:alpine
    ports:
      - "8080:80"
`,
} as const;
