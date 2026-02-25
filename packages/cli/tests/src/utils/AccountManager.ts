import { randomBytes } from 'node:crypto';
import {
  CI_ACTIVATION_CODE,
  getApiUrl,
  TEST_CONTEXT_PREFIX,
  TEST_EMAIL_DOMAIN,
  TEST_ORG_PREFIX,
} from '../constants.js';
import { CliTestRunner } from './CliTestRunner.js';

/**
 * Subscription plans available for test accounts
 */
export type SubscriptionPlan = 'COMMUNITY' | 'PROFESSIONAL' | 'BUSINESS' | 'ENTERPRISE';

/**
 * Test account credentials and metadata
 */
export interface TestAccount {
  organizationName: string;
  email: string;
  password: string;
  /** Master password for vault encryption (separate from login password) */
  masterPassword: string;
  contextName: string;
  plan?: SubscriptionPlan;
}

/**
 * Account manager for CLI E2E tests.
 *
 * Handles:
 * - Generating unique test account credentials
 * - Creating and registering test accounts
 * - Managing test contexts
 * - Cleanup after tests
 */
export class AccountManager {
  private readonly apiUrl: string;

  constructor(apiUrl?: string) {
    this.apiUrl = apiUrl ?? getApiUrl();
  }

  /**
   * Generate unique test account credentials.
   * Each call generates a new unique account.
   */
  generateAccount(plan?: SubscriptionPlan): TestAccount {
    const id = randomBytes(4).toString('hex');
    return {
      organizationName: `${TEST_ORG_PREFIX}${id}`,
      email: `test-${id}@${TEST_EMAIL_DOMAIN}`,
      password: `TestPass${id}!`,
      masterPassword: `MasterPass${id}!`,
      contextName: `${TEST_CONTEXT_PREFIX}${id}`,
      plan,
    };
  }

  /**
   * Create and register a master test context.
   *
   * Steps:
   * 1. Generate unique credentials
   * 2. Create CLI context
   * 3. Register organization
   * 4. Activate account (using CI activation code)
   * 5. Login
   *
   * @returns Registered test account
   */
  async createMasterContext(): Promise<TestAccount> {
    const account = this.generateAccount();
    const runner = new CliTestRunner({ apiUrl: this.apiUrl });

    console.warn(`[AccountManager] Creating master context: ${account.contextName}`);
    console.warn(`[AccountManager] Email: ${account.email}`);

    // 1. Create CLI context (allows storing credentials separately)
    const createResult = await runner.run([
      'config',
      'init',
      account.contextName,
      '--api-url',
      this.apiUrl,
    ]);

    if (!createResult.success) {
      throw new Error(`Context creation failed: ${runner.getErrorMessage(createResult)}`);
    }

    // Use the new context for subsequent commands
    const contextRunner = CliTestRunner.withContext(account.contextName);
    contextRunner.config.apiUrl = this.apiUrl;

    // 2. Register organization
    const registerResult = await contextRunner.register(
      account.organizationName,
      account.email,
      account.password,
      account.plan
    );

    if (!registerResult.success) {
      // Cleanup context on failure
      await runner.run(['config', 'delete', account.contextName]);
      throw new Error(`Registration failed: ${contextRunner.getErrorMessage(registerResult)}`);
    }

    // 3. Activate account (uses CI_MODE activation code)
    const activateResult = await contextRunner.activate(
      account.email,
      account.password,
      CI_ACTIVATION_CODE
    );

    if (!activateResult.success) {
      await runner.run(['config', 'delete', account.contextName]);
      throw new Error(`Activation failed: ${contextRunner.getErrorMessage(activateResult)}`);
    }

    // 4. Login
    const loginResult = await contextRunner.login(account.email, account.password);

    if (!loginResult.success) {
      await runner.run(['config', 'delete', account.contextName]);
      throw new Error(`Login failed: ${contextRunner.getErrorMessage(loginResult)}`);
    }

    console.warn(`[AccountManager] Master context created successfully`);

    return account;
  }

  /**
   * Create a test context with a specific subscription plan.
   * Used for edition-specific tests (feature flags, rate limits, etc.)
   *
   * @param plan Subscription plan for the account
   * @returns Registered test account with specified plan
   */
  async createEditionContext(plan: SubscriptionPlan): Promise<TestAccount> {
    const account = this.generateAccount(plan);
    const runner = new CliTestRunner({ apiUrl: this.apiUrl });

    console.warn(`[AccountManager] Creating edition context: ${account.contextName} (${plan})`);

    // 1. Create CLI context
    const createResult = await runner.run([
      'config',
      'init',
      account.contextName,
      '--api-url',
      this.apiUrl,
    ]);

    if (!createResult.success) {
      throw new Error(`Context creation failed: ${runner.getErrorMessage(createResult)}`);
    }

    const contextRunner = CliTestRunner.withContext(account.contextName);
    contextRunner.config.apiUrl = this.apiUrl;

    // 2. Register with plan
    const registerResult = await contextRunner.register(
      account.organizationName,
      account.email,
      account.password,
      plan
    );

    if (!registerResult.success) {
      await runner.run(['config', 'delete', account.contextName]);
      throw new Error(`Registration failed: ${contextRunner.getErrorMessage(registerResult)}`);
    }

    // 3. Activate
    const activateResult = await contextRunner.activate(
      account.email,
      account.password,
      CI_ACTIVATION_CODE
    );

    if (!activateResult.success) {
      await runner.run(['config', 'delete', account.contextName]);
      throw new Error(`Activation failed: ${contextRunner.getErrorMessage(activateResult)}`);
    }

    // 4. Login
    const loginResult = await contextRunner.login(account.email, account.password);

    if (!loginResult.success) {
      await runner.run(['config', 'delete', account.contextName]);
      throw new Error(`Login failed: ${contextRunner.getErrorMessage(loginResult)}`);
    }

    console.warn(`[AccountManager] Edition context created successfully`);

    return account;
  }

  /**
   * Clean up a test context.
   * Logs out and deletes the context.
   *
   * @param contextName Context name to clean up
   */
  async cleanupContext(contextName: string): Promise<void> {
    const runner = new CliTestRunner({ apiUrl: this.apiUrl });

    console.warn(`[AccountManager] Cleaning up context: ${contextName}`);

    // Logout (ignore errors - may already be logged out)
    await runner.run(['auth', 'logout'], { context: contextName }).catch(() => {});

    // Delete context (no --force flag needed for context delete)
    await runner.run(['config', 'delete', contextName]).catch(() => {});

    console.warn(`[AccountManager] Context cleanup complete`);
  }

  /**
   * Verify that default infrastructure exists after registration.
   * Checks for default region and bridge.
   *
   * @param contextName Context to verify
   */
  async verifyDefaultInfrastructure(contextName: string): Promise<void> {
    const runner = CliTestRunner.withContext(contextName);
    runner.config.apiUrl = this.apiUrl;

    // Verify default region exists
    const regionsResult = await runner.regionList();
    if (!runner.isSuccess(regionsResult)) {
      throw new Error(`Failed to list regions: ${runner.getErrorMessage(regionsResult)}`);
    }

    const regions = runner.expectSuccessArray<{ regionName: string }>(regionsResult);
    if (regions.length === 0) {
      throw new Error('No default region found after organization registration');
    }

    // Verify default bridge exists
    const defaultRegion = regions[0].regionName;
    const bridgesResult = await runner.bridgeList(defaultRegion);
    if (!runner.isSuccess(bridgesResult)) {
      throw new Error(`Failed to list bridges: ${runner.getErrorMessage(bridgesResult)}`);
    }

    const bridges = runner.expectSuccessArray<{ bridgeName: string }>(bridgesResult);
    if (bridges.length === 0) {
      throw new Error(
        `No default bridge found in region "${defaultRegion}" after organization registration`
      );
    }

    console.warn(`[AccountManager] Default infrastructure verified (region: ${defaultRegion})`);
  }
}
