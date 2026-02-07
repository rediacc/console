/**
 * Unified test context abstraction for CLI tests.
 *
 * Provides a single interface for both cloud and local (E2E) test modes,
 * enabling shared test scenarios to run in either mode without code duplication.
 */
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import { type CliResult, CliTestRunner } from './CliTestRunner';
import { E2E } from './e2e-constants';
import {
  createEditionContext,
  type EditionTestContext,
  type SubscriptionPlan,
} from './edition';
import { getE2EConfig, setupE2EEnvironment } from './local';
import { SSHValidator } from './SSHValidator';

/**
 * Unified test context used by shared scenarios.
 */
export interface TestContext {
  /** CLI test runner instance */
  runner: CliTestRunner;
  /** Execution mode */
  mode: 'cloud' | 'local';
  /** Machine name (cloud: first machine in team; local: 'vm1') */
  machineName: string;
  /** Team name (cloud: from global state; local: null) */
  teamName: string | null;
  /** SSH validator (local only, for infrastructure assertions) */
  ssh: SSHValidator | null;
  /** Cleanup function to call in afterAll */
  cleanup: () => Promise<void>;
  /** Default timeout for test operations */
  defaultTimeout: number;
}

/**
 * Create a cloud test context backed by the API.
 *
 * Registers an isolated edition-specific account, resolves team/machine names,
 * and returns a TestContext suitable for shared scenarios.
 */
export async function createCloudTestContext(
  edition: SubscriptionPlan = 'ENTERPRISE'
): Promise<TestContext> {
  const editionCtx: EditionTestContext = await createEditionContext(edition);

  // Resolve team name
  const teamResult = await editionCtx.runner.teamList();
  const teams = editionCtx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
  const teamName = teams[0]?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;

  // Resolve region + bridge for machine creation
  const regionResult = await editionCtx.runner.run(['region', 'list']);
  const regions = editionCtx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
  const regionName = regions[0]?.regionName ?? SYSTEM_DEFAULTS.REGION_NAME;

  const bridgeResult = await editionCtx.runner.run(['bridge', 'list', '--region', regionName]);
  const bridges = editionCtx.runner.expectSuccessArray<{ bridgeName: string }>(bridgeResult);
  const bridgeName = bridges[0]?.bridgeName ?? SYSTEM_DEFAULTS.BRIDGE_NAME;

  // Create a machine for the test context
  const machineName = `ctx-machine-${Date.now()}`;
  await editionCtx.runner.run([
    'machine',
    'create',
    machineName,
    '--team',
    teamName,
    '--bridge',
    bridgeName,
  ]);

  return {
    runner: editionCtx.runner,
    mode: 'cloud',
    machineName,
    teamName,
    ssh: null,
    defaultTimeout: 30_000,
    cleanup: async () => {
      await editionCtx.runner
        .run(['machine', 'delete', machineName, '--team', teamName, '--force'])
        .catch(() => {});
      await editionCtx.cleanup();
    },
  };
}

/**
 * Create a local (E2E) test context backed by real VMs.
 *
 * Sets up a local CLI context with SSH keys, adds VMs, and returns
 * a TestContext with an SSHValidator for infrastructure assertions.
 *
 * Returns null if E2E environment is not configured.
 */
export async function createLocalTestContext(
  prefix: string
): Promise<TestContext | null> {
  const config = getE2EConfig();
  if (!config.enabled) {
    return null;
  }

  const contextName = `${prefix}-${Date.now()}`;
  const cleanupFn = await setupE2EEnvironment(contextName);

  const runner = CliTestRunner.withContext(contextName);
  const ssh = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);

  return {
    runner,
    mode: 'local',
    machineName: E2E.MACHINE_VM1,
    teamName: null,
    ssh,
    defaultTimeout: E2E.TEST_TIMEOUT,
    cleanup: async () => {
      await cleanupFn?.();
    },
  };
}

/**
 * Helper to safely run a CLI command for cleanup.
 * Never throws — suitable for afterAll blocks.
 */
export async function safeRun(
  runner: CliTestRunner,
  args: string[]
): Promise<CliResult | null> {
  try {
    return await runner.run(args, { timeout: 120_000 });
  } catch {
    return null;
  }
}
