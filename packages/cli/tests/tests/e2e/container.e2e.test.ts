import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { E2E } from '../../src/utils/e2e-constants';
import { getE2EConfig, setupE2EEnvironment } from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';

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
 *
 * @covers daemon_setup, daemon_start, daemon_teardown
 */
test.describe
  .serial('Phase 5: Container Operations @e2e', () => {
    const config = getE2EConfig();
    let ssh1: SSHValidator;
    let cleanup: (() => Promise<void>) | null = null;
    let runner: CliTestRunner;
    const ctxName = `e2e-phase5-${Date.now()}`;
    const containerName = 'web';

    /** Docker socket for network-specific daemon (matches production isolation) */
    const dockerSocket = `unix:///var/run/rediacc/docker-${E2E.NETWORK_ID}.sock`;
    /** Helper to run docker commands on the network-specific daemon via SSH */
    const dockerCmd = (cmd: string) => `sudo env DOCKER_HOST=${dockerSocket} docker ${cmd}`;

    /** Build container command args */
    const containerCmd = (cmd: string, extraFlags: string[] = []) => [
      'container', cmd,
      '--machine', E2E.MACHINE_VM1,
      '--repository', E2E.REPO_CONTAINER,
      '--network-id', E2E.NETWORK_ID_STR,
      '--container', containerName,
      ...extraFlags,
    ];

    test.beforeAll(async () => {
      test.skip(!config.enabled, 'E2E VMs not configured');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
      runner = CliTestRunner.withContext(ctxName);

      // Force-delete stale repo from previous runs (ignore errors)
      try { await runner.run(['repository', 'down', E2E.REPO_CONTAINER, '--machine', E2E.MACHINE_VM1, '--option', 'unmount'], { timeout: 60_000 }); } catch { /* ignore */ }
      try { await runner.run(['repository', 'delete', E2E.REPO_CONTAINER, '--machine', E2E.MACHINE_VM1], { timeout: 60_000 }); } catch { /* ignore */ }

      // Create repository for container tests
      const createResult = await runner.run(
        ['repository', 'create', E2E.REPO_CONTAINER, '--machine', E2E.MACHINE_VM1, '--size', E2E.REPO_SIZE],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(createResult);

      // Set up network-specific Docker daemon
      const setupResult = await runner.run(
        ['daemon', 'setup', '--machine', E2E.MACHINE_VM1, '--network-id', E2E.NETWORK_ID_STR],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(setupResult);

      const startResult = await runner.run(
        ['daemon', 'start', '--machine', E2E.MACHINE_VM1, '--network-id', E2E.NETWORK_ID_STR],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(startResult);

      // Wait for Docker daemon to be ready on the network socket
      const waitResult = await ssh1.exec(
        `for i in $(seq 1 30); do ${dockerCmd('info')} >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1`
      );
      if (!waitResult.success) {
        throw new Error('Docker daemon did not become ready on network socket');
      }

      // Create test container on the network-specific daemon (stopped state)
      const createContainerResult = await ssh1.exec(
        dockerCmd(`create --name ${containerName} -p 8080:80 nginx:alpine`)
      );
      if (!createContainerResult.success) {
        throw new Error(`Failed to create test container: ${createContainerResult.stderr}`);
      }
    });

    test.afterAll(async () => {
      // Best-effort cleanup
      try {
        await ssh1?.exec(dockerCmd(`rm -f ${containerName}`));
      } catch { /* ignore */ }
      try {
        await runner?.run(
          ['daemon', 'teardown', '--machine', E2E.MACHINE_VM1, '--network-id', E2E.NETWORK_ID_STR],
          { timeout: E2E.TEST_TIMEOUT }
        );
      } catch { /* ignore */ }
      if (runner) {
        try {
          await runner.run(
            ['repository', 'down', E2E.REPO_CONTAINER, '--machine', E2E.MACHINE_VM1, '--option', 'unmount'],
            { timeout: 120_000 }
          );
        } catch { /* ignore */ }
        try {
          await runner.run(
            ['repository', 'delete', E2E.REPO_CONTAINER, '--machine', E2E.MACHINE_VM1],
            { timeout: 120_000 }
          );
        } catch { /* ignore */ }
      }
      await cleanup?.();
    });

    test('container_start - should start container', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(containerCmd('start'), { timeout: E2E.TEST_TIMEOUT });
      runner.expectSuccess(result);

      // SSH validation: container should be running on the network-specific daemon
      const check = await ssh1.exec(
        dockerCmd(`ps --format '{{.Names}}' --filter name=${containerName}`)
      );
      expect(check.stdout.trim()).toContain(containerName);
    });

    test('container_list - should list running containers', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        ['container', 'list', '--machine', E2E.MACHINE_VM1, '--network-id', E2E.NETWORK_ID_STR],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('container_stats - should show container resource usage', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(containerCmd('stats'), { timeout: E2E.TEST_TIMEOUT });
      runner.expectSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('container_logs - should retrieve container logs', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        containerCmd('logs', ['--lines', '50']),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);
    });

    test('container_inspect - should return container configuration', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(containerCmd('inspect'), { timeout: E2E.TEST_TIMEOUT });
      runner.expectSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('container_exec - should execute command inside container', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        containerCmd('exec', ['--command', 'echo hello']),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output).toContain('hello');
    });

    test('container_pause - should pause running container', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(containerCmd('pause'), { timeout: E2E.TEST_TIMEOUT });
      runner.expectSuccess(result);

      // SSH validation: container should be paused on the network daemon
      const pauseCheck = await ssh1.exec(
        dockerCmd(`ps --filter "status=paused" --format '{{.Names}}'`)
      );
      expect(pauseCheck.stdout).toContain(containerName);
    });

    test('container_unpause - should unpause container', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(containerCmd('unpause'), { timeout: E2E.TEST_TIMEOUT });
      runner.expectSuccess(result);

      // SSH validation: no paused containers on the network daemon
      const pauseCheck = await ssh1.exec(
        dockerCmd(`ps --filter "status=paused" --format '{{.Names}}'`)
      );
      expect(pauseCheck.stdout.trim()).toBe('');
    });

    test('container_stop - should stop running container', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(containerCmd('stop'), { timeout: E2E.TEST_TIMEOUT });
      runner.expectSuccess(result);

      // SSH validation: container should not be running on the network daemon
      const check = await ssh1.exec(
        dockerCmd(
          `ps --filter "status=running" --filter name=${containerName} --format '{{.Names}}'`
        )
      );
      expect(check.stdout.trim()).toBe('');
    });

    test('container_restart - should restart stopped container', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(containerCmd('restart'), { timeout: E2E.TEST_TIMEOUT });
      runner.expectSuccess(result);

      // SSH validation: container should be running again
      const check = await ssh1.exec(
        dockerCmd(
          `ps --filter "status=running" --filter name=${containerName} --format '{{.Names}}'`
        )
      );
      expect(check.stdout).toContain(containerName);
    });

    test('container_kill - should forcefully stop container', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(containerCmd('kill'), { timeout: E2E.TEST_TIMEOUT });
      runner.expectSuccess(result);

      // SSH validation: container should be stopped/exited
      const check = await ssh1.exec(
        dockerCmd(
          `ps --filter "status=running" --filter name=${containerName} --format '{{.Names}}'`
        )
      );
      expect(check.stdout.trim()).toBe('');
    });

    test('container_remove - should remove stopped container', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        containerCmd('remove', ['--force']),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      // SSH validation: container should be completely removed from the network daemon
      const check = await ssh1.exec(
        dockerCmd(`ps -a --filter name=${containerName} --format '{{.Names}}'`)
      );
      expect(check.stdout.trim()).toBe('');
    });
  });
