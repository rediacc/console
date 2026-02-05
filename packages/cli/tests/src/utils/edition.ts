/**
 * Edition-Specific Test Utilities for Playwright
 *
 * Provides utilities for testing edition-based feature restrictions,
 * resource limits, and subscription-specific behavior.
 */

import { randomBytes } from 'node:crypto';
import { expect } from '@playwright/test';
import { CI_ACTIVATION_CODE, getApiUrl, TEST_EMAIL_DOMAIN } from '../constants';
import { type CliResult, CliTestRunner } from './CliTestRunner';

export type SubscriptionPlan = 'COMMUNITY' | 'PROFESSIONAL' | 'BUSINESS' | 'ENTERPRISE';

export interface TestAccount {
  organizationName: string;
  email: string;
  password: string;
  contextName: string;
  plan?: SubscriptionPlan;
}

export interface EditionTestContext {
  /** CLI context name for this test account */
  contextName: string;
  /** Generated test account details */
  account: TestAccount;
  /** Subscription plan for this context */
  plan: SubscriptionPlan;
  /** CliTestRunner for this context */
  runner: CliTestRunner;
  /** Cleanup function to call in afterAll */
  cleanup: () => Promise<void>;
}

/**
 * Generate a unique test account for this test run
 * @param plan Optional subscription plan (defaults to COMMUNITY)
 */
export function generateTestAccount(plan?: SubscriptionPlan): TestAccount {
  const id = randomBytes(4).toString('hex');
  return {
    organizationName: `TestOrg-${id}`,
    email: `test-${id}@${TEST_EMAIL_DOMAIN}`,
    password: `TestPass${id}!`,
    contextName: `test-${id}`,
    plan,
  };
}

/**
 * Generate a unique resource name for testing
 */
export function uniqueName(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

/**
 * Create an isolated test context for a specific edition.
 * Each context gets its own organization, user, and CLI context.
 *
 * @param plan - The subscription plan to use for the test account
 * @returns EditionTestContext with account details and cleanup function
 */
export async function createEditionContext(plan: SubscriptionPlan): Promise<EditionTestContext> {
  const apiUrl = getApiUrl();
  const account = generateTestAccount(plan);

  // Create a base runner without context
  const baseRunner = new CliTestRunner();

  // Create CLI context for isolated credentials
  const contextResult = await baseRunner.run(
    ['context', 'create', account.contextName, '--api-url', apiUrl],
    { context: '' }
  );

  if (!contextResult.success) {
    throw new Error(
      `Failed to create context for ${plan}: ${baseRunner.getErrorMessage(contextResult)}`
    );
  }

  // Create runner with the new context and credentials
  // Credentials are needed for vault operations (master password)
  const runner = new CliTestRunner({
    context: account.contextName,
    apiUrl,
    credentials: {
      email: account.email,
      password: account.password,
      masterPassword: account.password, // Use login password as master password for test accounts
    },
  });

  // Register with plan
  const registerArgs = [
    'auth',
    'register',
    '--organization',
    account.organizationName,
    '-e',
    account.email,
    '-p',
    account.password,
    '--endpoint',
    apiUrl,
  ];

  registerArgs.push('--plan', plan);

  const registerResult = await runner.run(registerArgs);
  if (!registerResult.success) {
    throw new Error(`Registration failed: ${runner.getErrorMessage(registerResult)}`);
  }

  // Activate with CI_MODE activation code
  const activateResult = await runner.run([
    'auth',
    'activate',
    '-e',
    account.email,
    '-p',
    account.password,
    '--code',
    CI_ACTIVATION_CODE,
    '--endpoint',
    apiUrl,
  ]);

  if (!activateResult.success) {
    throw new Error(`Activation failed: ${runner.getErrorMessage(activateResult)}`);
  }

  // Login
  const loginResult = await runner.run([
    'login',
    '-e',
    account.email,
    '-p',
    account.password,
    '--endpoint',
    apiUrl,
  ]);

  if (!loginResult.success) {
    throw new Error(`Login failed: ${runner.getErrorMessage(loginResult)}`);
  }

  console.warn(`[DEBUG] createEditionContext completed successfully for ${plan}`);
  console.warn(`[DEBUG] Context: ${account.contextName}, Email: ${account.email}`);
  console.warn(`[DEBUG] Runner config:`, JSON.stringify(runner.config, null, 2));

  return {
    contextName: account.contextName,
    account,
    plan,
    runner,
    cleanup: async () => {
      // Logout from this context
      await runner.run(['logout']).catch(() => {});
      // Delete the context (no --force flag for context delete)
      await baseRunner
        .run(['context', 'delete', account.contextName], { context: '' })
        .catch(() => {});
    },
  };
}

/**
 * Error patterns for edition-specific restrictions.
 * These patterns match RAISERROR messages in middleware stored procedures.
 */
export const EditionErrorPatterns = {
  // 402 Payment Required - Feature blocks
  CEPH_NOT_AVAILABLE: 'only available for ENTERPRISE and BUSINESS',
  CEPH_POOL_LIMIT_BUSINESS: 'Business plan customers are limited to 1 Ceph pool',
  PERMISSION_GROUP_COMMUNITY: 'not available in the Community edition',
  RESOURCE_LIMIT_EXCEEDED: 'Resource limit exceeded',

  // Specific resource limit messages
  BRIDGE_LIMIT_EXCEEDED: 'Resource limit exceeded for customer bridges',

  // 429 Too Many Requests - Rate limits
  TOO_MANY_PENDING_ITEMS: 'too many pending queue items',

  // Generic upgrade message
  UPGRADE_REQUIRED: 'Please upgrade',
} as const;

/**
 * Resource limits by edition, matching fn_GetPlanResources in SQL.
 */
export const RESOURCE_LIMITS = {
  COMMUNITY: {
    bridges: 0,
    maxActiveJobs: 1,
    maxReservedJobs: 1,
    jobTimeoutHours: 2,
    maxRepositorySizeGb: 10,
    maxPendingPerUser: 5,
    maxTasksPerMachine: 1,
    maxJobsPerMonth: 500,
  },
  PROFESSIONAL: {
    bridges: 1,
    maxActiveJobs: 5,
    maxReservedJobs: 2,
    jobTimeoutHours: 24,
    maxRepositorySizeGb: 100,
    maxPendingPerUser: 10,
    maxTasksPerMachine: 2,
    maxJobsPerMonth: 5000,
  },
  BUSINESS: {
    bridges: 2,
    maxActiveJobs: 20,
    maxReservedJobs: 3,
    jobTimeoutHours: 72,
    maxRepositorySizeGb: 500,
    maxPendingPerUser: 20,
    maxTasksPerMachine: 3,
    cephPoolsPerTeam: 1,
    maxJobsPerMonth: 20000,
  },
  ENTERPRISE: {
    bridges: 10,
    maxActiveJobs: 60,
    maxReservedJobs: 5,
    jobTimeoutHours: 96,
    maxRepositorySizeGb: 1024,
    maxPendingPerUser: 50,
    maxTasksPerMachine: 5,
    cephPoolsPerTeam: -1, // Unlimited
    maxJobsPerMonth: 100000,
  },
} as const;

/**
 * Feature availability matrix by edition.
 */
export const FEATURE_MATRIX = {
  permissionGroups: ['PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'],
  ceph: ['BUSINESS', 'ENTERPRISE'],
  queuePriority: ['BUSINESS', 'ENTERPRISE'],
  advancedAnalytics: ['BUSINESS', 'ENTERPRISE'],
  prioritySupport: ['PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'],
  auditLog: ['PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'],
  advancedQueue: ['BUSINESS', 'ENTERPRISE'],
  customBranding: ['PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'],
  dedicatedAccount: ['ENTERPRISE'],
} as const;

export type FeatureName = keyof typeof FEATURE_MATRIX;

/**
 * Test machine vault for queue operations.
 * Contains minimal required fields (IP, USER) for queue vault building.
 * The IP is a valid format but not necessarily a real machine.
 */
export const TEST_MACHINE_VAULT = JSON.stringify({
  IP: '192.168.111.99',
  USER: 'testuser',
  DATASTORE: '/mnt/test',
});

/**
 * Check if a feature is available for a given subscription plan
 */
export function isFeatureAvailable(feature: FeatureName, plan: SubscriptionPlan): boolean {
  return (FEATURE_MATRIX[feature] as readonly string[]).includes(plan);
}

// Map HTTP status codes to Unix-compatible exit codes
const HTTP_TO_EXIT_CODE: Record<number, number> = {
  402: 8, // PAYMENT_REQUIRED
  429: 9, // RATE_LIMITED
};

/**
 * Assert that a CLI result represents an edition-specific error
 */
export function expectEditionError(
  result: CliResult,
  expectedHttpStatus: 402 | 429,
  messagePattern: string
): void {
  const expectedExitCode = HTTP_TO_EXIT_CODE[expectedHttpStatus];

  expect(
    result.success,
    `Expected failure with HTTP ${expectedHttpStatus} (exit ${expectedExitCode}) but got success. stdout: ${result.stdout}`
  ).toBe(false);

  expect(
    result.exitCode,
    `Expected exit code ${expectedExitCode} (HTTP ${expectedHttpStatus}) but got ${result.exitCode}`
  ).toBe(expectedExitCode);

  const errorResponse = result.json as { success: false; error: { message: string } } | null;
  const errorMsg = errorResponse?.error.message ?? result.stderr ?? result.stdout;

  expect(
    errorMsg.toLowerCase(),
    `Expected error to contain "${messagePattern}" but got: ${errorMsg}`
  ).toContain(messagePattern.toLowerCase());
}

/**
 * Assert that a CLI result represents a successful operation
 */
export function expectEditionSuccess(result: CliResult): void {
  const errorResponse = result.json as { success: false; error?: { message?: string } } | null;
  const errorMsg = errorResponse?.error?.message ?? result.stderr ?? '(no error message)';

  // Build comprehensive debug info for assertion message
  const debugInfo = `
exitCode: ${result.exitCode}
stdout (first 500 chars): ${result.stdout.slice(0, 500)}
stderr (first 500 chars): ${result.stderr.slice(0, 500)}
json: ${JSON.stringify(result.json).slice(0, 500)}`;

  expect(result.success, `Expected success but got failure. Error: ${errorMsg}${debugInfo}`).toBe(
    true
  );
}

/**
 * Get all editions that have access to a feature
 */
export function getEditionsWithFeature(feature: FeatureName): SubscriptionPlan[] {
  return [...FEATURE_MATRIX[feature]] as SubscriptionPlan[];
}

/**
 * Get all editions that do NOT have access to a feature
 */
export function getEditionsWithoutFeature(feature: FeatureName): SubscriptionPlan[] {
  const allEditions: SubscriptionPlan[] = ['COMMUNITY', 'PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'];
  const withFeature = FEATURE_MATRIX[feature] as readonly string[];
  return allEditions.filter((edition) => !withFeature.includes(edition));
}

/**
 * Extract task ID from CLI output
 */
export function extractTaskId(stdout: string): string {
  const match = /Task ID:\s*([a-f0-9-]+)/i.exec(stdout);
  return match?.[1] ?? '';
}

/**
 * Wait for a specified number of milliseconds
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Get resource limit for a specific plan and resource type
 */
export function getResourceLimit(
  plan: SubscriptionPlan,
  resource: keyof (typeof RESOURCE_LIMITS)['COMMUNITY']
): number {
  return RESOURCE_LIMITS[plan][resource];
}
