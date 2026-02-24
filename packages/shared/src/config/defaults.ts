/**
 * Centralized default values for nullish coalescing operations
 *
 * This file consolidates hardcoded defaults used throughout the codebase
 * to ensure consistency and make them easier to maintain.
 *
 * Usage:
 *   import { DEFAULTS } from '@rediacc/shared/config';
 *   const port = options?.port ?? DEFAULTS.SSH.PORT;
 */

/**
 * SSH and network connection defaults
 */
export const SSH_DEFAULTS = {
  /** Standard SSH port */
  PORT: 22,

  /** Default terminal columns */
  TERMINAL_COLS: 80,

  /** Default terminal rows */
  TERMINAL_ROWS: 24,

  /** Terminal type identifier */
  TERMINAL_TYPE: 'xterm-256color',

  /** SSH keepalive interval in ms */
  KEEPALIVE_INTERVAL: 10000,

  /** SSH connection timeout in ms */
  CONNECTION_TIMEOUT: 10000,

  /** SSH ready timeout in ms */
  READY_TIMEOUT: 10000,

  /** SSH server alive interval in seconds */
  SERVER_ALIVE_INTERVAL: 60,

  /** SSH server alive count max */
  SERVER_ALIVE_COUNT_MAX: 3,
} as const;

/**
 * Repository and container defaults
 */
export const REPOSITORY_DEFAULTS = {
  /** Default repository tag */
  TAG: 'latest',

  /** Default network mode for containers */
  NETWORK_MODE: 'bridge',

  /** Default container user */
  UNIVERSAL_USER: 'rediacc',

  /** Default universal user ID */
  UNIVERSAL_USER_ID: '1000',

  /** Default container log lines to show */
  LOG_LINES: '50',

  /** Default container lines for protocol URLs */
  CONTAINER_LINES: 100,

  /** Default container action */
  CONTAINER_ACTION: 'terminal',
} as const;

/**
 * Docker and system paths
 */
export const DOCKER_DEFAULTS = {
  /** Default Docker host socket path */
  SOCKET_PATH: '/var/run/docker.sock',

  /** Default Docker host URI */
  HOST_URI: 'unix:///var/run/docker.sock',
} as const;

/**
 * Shell and binary paths
 */
export const SHELL_DEFAULTS = {
  /** Default bash shell path */
  BASH: '/bin/bash',

  /** Default sh shell path */
  SH: '/bin/sh',
} as const;

/**
 * Telemetry and monitoring fallback values
 */
export const TELEMETRY_DEFAULTS = {
  /** Fallback value for unknown/missing telemetry data */
  UNKNOWN: 'unknown',

  /** Uppercase variant for backwards compatibility */
  UNKNOWN_UPPER: 'UNKNOWN',

  /** Default CLI service name */
  SERVICE_NAME: 'rediacc-cli',

  /** Default environment */
  ENVIRONMENT: 'production',

  /** Default metric unit */
  UNIT: 'ms',
} as const;

/**
 * Protocol and URL defaults
 */
export const PROTOCOL_DEFAULTS = {
  /** Default protocol action */
  ACTION: 'download',

  /** Desktop protocol action */
  ACTION_DESKTOP: 'desktop',

  /** Default public site URL */
  SITE_URL: 'https://www.rediacc.com',
} as const;

/**
 * Platform-specific defaults
 */
export const PLATFORM_DEFAULTS = {
  /** Default Windows system directory */
  WINDOWS_SYSTEM: 'C:\\Windows',

  /** Default renet build platform (Node process.platform maps to this) */
  DEFAULT_RENET: 'linux',
} as const;

/**
 * Localization defaults
 */
export const LOCALE_DEFAULTS = {
  /** Default language code */
  LANGUAGE: 'en',
} as const;

/**
 * Status and state defaults
 */
export const STATUS_DEFAULTS = {
  /** Unknown status fallback */
  UNKNOWN: 'Unknown',

  /** Unknown status fallback (uppercase) */
  UNKNOWN_UPPERCASE: 'UNKNOWN',

  /** Current version identifier */
  CURRENT: 'Current',

  /** Original version identifier */
  ORIGINAL: 'original',

  /** Display label when a timestamp has never occurred */
  NEVER: 'never',
} as const;

/**
 * Host and connection defaults
 */
export const HOST_DEFAULTS = {
  /** Default localhost hostname */
  LOCALHOST: 'localhost',

  /** Default web port string */
  WEB_PORT_STRING: '7322',
} as const;

/**
 * UI and component defaults
 */
export const UI_DEFAULTS = {
  /** Loading delay before showing spinner (ms) */
  LOADING_DELAY: 200,

  /** Default width for Skeleton component */
  SKELETON_WIDTH: '100%',

  /** Default search input ID */
  SEARCH_INPUT_ID: 'resource-list-search',

  /** Default action column width */
  ACTION_COLUMN_WIDTH: 120,

  /** Default advanced column width */
  ADVANCED_COLUMN_WIDTH: 100,

  /** Default button type */
  BUTTON_TYPE: 'primary' as const,

  /** Default table alignment */
  TABLE_ALIGN: 'left' as const,
} as const;

/**
 * Priority and numeric defaults
 */
export const PRIORITY_DEFAULTS = {
  /** Default queue priority */
  QUEUE_PRIORITY: 3,

  /** Default queue list limit */
  QUEUE_LIST_LIMIT: 50,

  /** Default CPU count for containers */
  CPU_COUNT: '0',
} as const;

/**
 * Resource type defaults
 */
export const RESOURCE_DEFAULTS = {
  /** Default resource type */
  TYPE: 'repository',

  /** Default modal mode */
  MODE: 'create',

  /** Default infrastructure tab */
  TAB: 'region',

  /** Default audit filter */
  AUDIT_FILTER: 'All',

  /** Default field ID */
  FIELD_ID: 'generated',

  /** Default actor for audit */
  ACTOR: 'System',

  /** Default file type for SFTP */
  FILE_TYPE: 'file',
} as const;

/**
 * Edition and subscription defaults
 */
export const EDITION_DEFAULTS = {
  /** Default edition type */
  EDITION: 'FREE',

  /** Default build type */
  BUILD_TYPE: 'DEBUG',
} as const;

/**
 * VSCode and development defaults
 */
export const VSCODE_DEFAULTS = {
  /** VSCode installation status */
  NOT_INSTALLED: 'not-installed',
} as const;

/**
 * Context and CLI configuration defaults
 */
export const CONTEXT_DEFAULTS = {
  /** Default renet path indicator */
  RENET_PATH: 'renet (in PATH)',

  /** Default renet binary name */
  RENET_BINARY: 'renet',

  /** Default SSH key path */
  SSH_KEY_PATH: '~/.ssh/rediacc',

  /** Default config file name */
  CONFIG_NAME: 'rediacc',
} as const;

/**
 * Store adapter defaults
 */
export const STORE_DEFAULTS = {
  /** Default S3 region */
  S3_REGION: 'auto',

  /** Default git branch for git store */
  GIT_BRANCH: 'main',

  /** Default path within git repo for config files */
  GIT_PATH: 'configs',

  /** Default Vault KV v2 mount path */
  VAULT_MOUNT: 'secret',

  /** Default Vault config prefix */
  VAULT_PREFIX: 'rdc/configs',
} as const;

/**
 * Telemetry and analytics defaults
 */
export const ANALYTICS_DEFAULTS = {
  /** Default sample rate */
  SAMPLE_RATE: 0.1,
} as const;

/**
 * Subscription and licensing defaults
 */
export const SUBSCRIPTION_DEFAULTS = {
  /** Default subscription plan */
  PLAN: 'COMMUNITY',
} as const;

/**
 * Process and execution defaults
 */
export const PROCESS_DEFAULTS = {
  /** Default stdio option for child processes */
  STDIO: 'inherit' as const,

  /** Default shell for bash execution */
  SHELL: '/bin/bash',

  /** Default error message for renet provisioning failure */
  RENET_PROVISION_ERROR: 'Failed to provision renet',
} as const;

/**
 * Timeout and interval defaults (all in milliseconds unless noted)
 */
export const TIMEOUT_DEFAULTS = {
  /** VSCode bootstrap timeout */
  VSCODE_BOOTSTRAP: 30000,

  /** Screenshot timeout */
  SCREENSHOT: 30000,

  /** Default execution timeout (10 minutes) */
  EXECUTION: 10 * 60 * 1000,
} as const;

/**
 * CLI test defaults
 */
export const CLI_TEST_DEFAULTS = {
  /** Default output directory for test files */
  OUTPUT_DIR: 'test-outputs',

  /** Default output format for CLI commands */
  OUTPUT_FORMAT: 'json',

  /** Default SSH key path */
  SSH_KEY_PATH: '~/.ssh/id_rsa',

  /** Default SSH user for test VMs */
  VM_USER: 'root',
} as const;

/**
 * Sorting defaults
 */
export const SORT_DEFAULTS = {
  /** Fallback value for nullish sort order fields (pushes unordered items to end) */
  ORDER_FALLBACK: 99,
} as const;

/**
 * Aggregated defaults object for convenient access
 */
export const DEFAULTS = {
  SSH: SSH_DEFAULTS,
  REPOSITORY: REPOSITORY_DEFAULTS,
  DOCKER: DOCKER_DEFAULTS,
  SHELL: SHELL_DEFAULTS,
  TELEMETRY: TELEMETRY_DEFAULTS,
  TIMEOUT: TIMEOUT_DEFAULTS,
  PROTOCOL: PROTOCOL_DEFAULTS,
  PLATFORM: PLATFORM_DEFAULTS,
  LOCALE: LOCALE_DEFAULTS,
  STATUS: STATUS_DEFAULTS,
  HOST: HOST_DEFAULTS,
  UI: UI_DEFAULTS,
  PRIORITY: PRIORITY_DEFAULTS,
  RESOURCE: RESOURCE_DEFAULTS,
  EDITION: EDITION_DEFAULTS,
  SUBSCRIPTION: SUBSCRIPTION_DEFAULTS,
  VSCODE: VSCODE_DEFAULTS,
  CONTEXT: CONTEXT_DEFAULTS,
  STORE: STORE_DEFAULTS,
  ANALYTICS: ANALYTICS_DEFAULTS,
  PROCESS: PROCESS_DEFAULTS,
  CLI_TEST: CLI_TEST_DEFAULTS,
  SORT: SORT_DEFAULTS,
} as const;

/**
 * API and network endpoints
 */
export const API_DEFAULTS = {
  /** Sandbox API URL */
  SANDBOX_URL: 'https://sandbox.rediacc.com/api',

  /** Default console base URL */
  CONSOLE_URL: 'http://localhost:3000/console/',
} as const;

/**
 * SSH and terminal defaults
 */
export const TERMINAL_DEFAULTS = {
  /** Default shell */
  DEFAULT_SHELL: '/bin/bash',

  /** Fallback shell */
  FALLBACK_SHELL: '/bin/sh',

  /** Default terminal type */
  TYPE: 'terminal',
} as const;

/**
 * UI component identifiers
 */
export const UI_IDS = {
  /** Resource list refresh button */
  RESOURCE_LIST_REFRESH: 'resource-list-refresh',

  /** Resource list table */
  RESOURCE_LIST_TABLE: 'resource-list-table',

  /** Vault editor field generator */
  VAULT_EDITOR_FIELD: 'vault-editor-field-generator',
} as const;

/**
 * UI layout and sizing
 */
export const UI_SIZING = {
  /** Center alignment */
  CENTER: 'center' as const,

  /** Top left placement */
  TOP_LEFT: 'topLeft' as const,

  /** Default width for skeleton */
  SKELETON_HEIGHT: '16px',

  /** Modal width */
  MODAL_WIDTH: 180,

  /** Pagination size */
  PAGE_SIZE: 12,
} as const;

/**
 * Message severity levels
 */
export const SEVERITY_DEFAULTS = {
  /** Info level */
  INFO: 'info' as const,
} as const;

/**
 * SSH key defaults
 */
export const SSH_KEY_DEFAULTS = {
  /** RSA algorithm */
  ALGORITHM: 'rsa',

  /** Default key size */
  KEY_SIZE: 2048,
} as const;

/**
 * File size and timeout limits
 */
export const LIMITS_DEFAULTS = {
  /** Max file upload size (10MB) */
  MAX_FILE_SIZE: 10485760,

  /** Session timeout (1 hour) */
  SESSION_TIMEOUT: 3600,

  /** SSH keepalive interval */
  KEEPALIVE: '10000',

  /** SSH connection timeout */
  CONNECTION_TIMEOUT: '30000',

  /** API request timeout (900s) */
  API_TIMEOUT: 900,

  /** API retry timeout (600s) */
  API_RETRY_TIMEOUT: 600,
} as const;

/**
 * Version defaults
 */
export const VERSION_DEFAULTS = {
  /** Default version string */
  DEFAULT: '2.0.0',
} as const;

/**
 * Edition types
 */
export const EDITION_TYPES = {
  /** Community edition */
  COMMUNITY: 'COMMUNITY',
} as const;

/**
 * File type defaults
 */
export const FILE_DEFAULTS = {
  /** PNG image format */
  PNG: 'png',
} as const;

/**
 * Style defaults
 */
export const STYLE_DEFAULTS = {
  /** Inherit value */
  INHERIT: 'inherit' as const,
} as const;

/**
 * E2E test defaults
 */
export const E2E_DEFAULTS = {
  /** Default machine name for tests */
  MACHINE_NAME: 'machine-1',

  /** Default CPU count string */
  CPU_COUNT_STRING: '0',
} as const;

/**
 * Window sizing defaults
 */
export const WINDOW_DEFAULTS = {
  /** Default popout window width */
  POPOUT_WIDTH: 900,

  /** Default popout window height */
  POPOUT_HEIGHT: 600,
} as const;

/**
 * Website / documentation defaults
 */
export const WWW_DEFAULTS = {
  /** Default tutorial player title */
  TUTORIAL_TITLE: 'Terminal Tutorial',
} as const;

/**
 * Auto-update defaults
 */
export const UPDATE_DEFAULTS = {
  /** Default update provider */
  PROVIDER: 'generic' as const,

  /** Default update channel */
  CHANNEL: 'latest' as const,
} as const;

// Re-export aggregated defaults with new additions
export const DEFAULTS_EXTENDED = {
  ...DEFAULTS,
  API: API_DEFAULTS,
  TERMINAL: TERMINAL_DEFAULTS,
  UI_IDS,
  UI_SIZING,
  SEVERITY: SEVERITY_DEFAULTS,
  SSH_KEY: SSH_KEY_DEFAULTS,
  LIMITS: LIMITS_DEFAULTS,
  FILE: FILE_DEFAULTS,
  E2E: E2E_DEFAULTS,
  CLI_TEST: CLI_TEST_DEFAULTS,
  WINDOW: WINDOW_DEFAULTS,
  UPDATE: UPDATE_DEFAULTS,
  WWW: WWW_DEFAULTS,
} as const;
