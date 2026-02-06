import { expect, test } from '@playwright/test';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';
import { E2E } from '../../src/utils/e2e-constants';
import { createRepo, safeDeleteRepo } from '../../src/utils/local-operations';

/**
 * Phase 5: Container Operations
 *
 * Tests all 12 container operations:
 * container_start, container_list, container_stats, container_logs,
 * container_inspect, container_exec, container_pause, container_unpause,
 * container_stop, container_restart, container_kill, container_remove
 *
 * Setup: Creates a repository, starts a network-specific Docker daemon via
 * daemon_setup/daemon_start (matching production behavior where each repo
 * has its own isolated Docker daemon identified by network_id), then creates
 * a test container on that daemon.
 */
test.describe.serial('Phase 5: Container Operations @e2e', () => {
  const config = getE2EConfig();
  let ssh1: SSHValidator;
  let cleanup: (() => Promise<void>) | null = null;
  const ctxName = `e2e-phase5-${Date.now()}`;
  const containerName = 'web';

  /** Docker socket for network-specific daemon (matches production isolation) */
  const dockerSocket = `unix:///var/run/rediacc/docker-${E2E.NETWORK_ID}.sock`;
  /** Helper to run docker commands on the network-specific daemon via SSH */
  const dockerCmd = (cmd: string) => `sudo env DOCKER_HOST=${dockerSocket} docker ${cmd}`;

  /** Common params for all container operations (network_id routes to correct daemon) */
  const containerParams = (extra: Record<string, string> = {}) => ({
    repository: E2E.TEST_REPO,
    network_id: E2E.NETWORK_ID_STR,
    container: containerName,
    ...extra,
  });

  test.beforeAll(async () => {
    test.skip(!config.enabled, 'E2E VMs not configured');
    ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
    cleanup = await setupE2EEnvironment(ctxName);

    // Create repository for container tests
    await createRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, E2E.REPO_SIZE, ctxName);

    // Set up network-specific Docker daemon (mirrors production: each repo gets isolated daemon)
    const setupResult = await runLocalFunction('daemon_setup', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: { network_id: E2E.NETWORK_ID_STR },
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(setupResult, 'daemon_setup failed');

    const startResult = await runLocalFunction('daemon_start', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: { network_id: E2E.NETWORK_ID_STR },
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(startResult, 'daemon_start failed');

    // Wait for Docker daemon to be ready on the network socket
    const waitResult = await ssh1.exec(
      `for i in $(seq 1 30); do ${dockerCmd('info')} >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1`
    );
    if (!waitResult.success) {
      throw new Error('Docker daemon did not become ready on network socket');
    }

    // Create test container on the network-specific daemon (stopped state)
    // Using 'docker create' so container_start test actually starts it
    const createResult = await ssh1.exec(
      dockerCmd(`create --name ${containerName} -p 8080:80 nginx:alpine`)
    );
    if (!createResult.success) {
      throw new Error(`Failed to create test container: ${createResult.stderr}`);
    }
  });

  test.afterAll(async () => {
    // Best-effort cleanup: kill + remove container on network socket
    try {
      await ssh1?.exec(dockerCmd(`rm -f ${containerName}`));
    } catch {
      // ignore
    }
    // Tear down the Docker daemon
    try {
      await runLocalFunction('daemon_teardown', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { network_id: E2E.NETWORK_ID_STR },
        timeout: E2E.TEST_TIMEOUT,
      });
    } catch {
      // ignore
    }
    await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, ctxName);
    await cleanup?.();
  });

  test('container_start - should start container', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_start', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams(),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: container should be running on the network-specific daemon
    const check = await ssh1.exec(
      dockerCmd(`ps --format '{{.Names}}' --filter name=${containerName}`)
    );
    expect(check.stdout.trim()).toContain(containerName);
  });

  test('container_list - should list running containers', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_list', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: { repository: E2E.TEST_REPO, network_id: E2E.NETWORK_ID_STR },
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    const output = result.stdout + result.stderr;
    expect(output.length).toBeGreaterThan(0);
  });

  test('container_stats - should show container resource usage', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_stats', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams(),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    const output = result.stdout + result.stderr;
    expect(output.length).toBeGreaterThan(0);
  });

  test('container_logs - should retrieve container logs', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_logs', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams({ lines: '50' }),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);
  });

  test('container_inspect - should return container configuration', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_inspect', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams(),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    const output = result.stdout + result.stderr;
    expect(output.length).toBeGreaterThan(0);
  });

  test('container_exec - should execute command inside container', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_exec', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams({ command: 'echo hello' }),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    const output = result.stdout + result.stderr;
    expect(output).toContain('hello');
  });

  test('container_pause - should pause running container', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_pause', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams(),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: container should be paused on the network daemon
    const pauseCheck = await ssh1.exec(
      dockerCmd(`ps --filter "status=paused" --format '{{.Names}}'`)
    );
    expect(pauseCheck.stdout).toContain(containerName);
  });

  test('container_unpause - should unpause container', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_unpause', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams(),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: no paused containers on the network daemon
    const pauseCheck = await ssh1.exec(
      dockerCmd(`ps --filter "status=paused" --format '{{.Names}}'`)
    );
    expect(pauseCheck.stdout.trim()).toBe('');
  });

  test('container_stop - should stop running container', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_stop', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams(),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: container should not be running on the network daemon
    const check = await ssh1.exec(
      dockerCmd(`ps --filter "status=running" --filter name=${containerName} --format '{{.Names}}'`)
    );
    expect(check.stdout.trim()).toBe('');
  });

  test('container_restart - should restart stopped container', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_restart', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams(),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: container should be running again
    const check = await ssh1.exec(
      dockerCmd(`ps --filter "status=running" --filter name=${containerName} --format '{{.Names}}'`)
    );
    expect(check.stdout).toContain(containerName);
  });

  test('container_kill - should forcefully stop container', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_kill', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams(),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: container should be stopped/exited
    const check = await ssh1.exec(
      dockerCmd(`ps --filter "status=running" --filter name=${containerName} --format '{{.Names}}'`)
    );
    expect(check.stdout.trim()).toBe('');
  });

  test('container_remove - should remove stopped container', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    const result = await runLocalFunction('container_remove', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: containerParams({ force: 'true' }),
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: container should be completely removed from the network daemon
    const check = await ssh1.exec(
      dockerCmd(`ps -a --filter name=${containerName} --format '{{.Names}}'`)
    );
    expect(check.stdout.trim()).toBe('');
  });
});
