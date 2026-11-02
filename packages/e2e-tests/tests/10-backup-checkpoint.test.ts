import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH } from '../src/constants';
import { e2eRepoGuid } from '../src/utils/licence';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';
import type { ExecResult } from '../src/utils/renet-functions/types';

/**
 * A repository with no licence is refused with exit 10 (LICENSE_REQUIRED) before any command is built, and that refusal passes a syntax check while running nothing.
 * Every repository here is licensed first, so a refusal is a failure of the test, and the syntax check then judges a command that really ran.
 */
function expectRan(runner: RenetFunctionsTestRunner, result: ExecResult): void {
  expect(result.code, runner.getCombinedOutput(result)).not.toBe(10);
  expect(runner.hasValidCommandSyntax(result), runner.getCombinedOutput(result)).toBe(true);
}

/** License a fresh repository on the runner's target, so the calls below reach the function itself. */
async function licensedRepository(runner: RenetFunctionsTestRunner): Promise<string> {
  const guid = e2eRepoGuid();
  const licensed = await runner.licenseRepository(guid);
  expect(runner.isSuccess(licensed), runner.getCombinedOutput(licensed)).toBe(true);
  return guid;
}

/**
 * Backup/Checkpoint Operations Tests
 *
 * Tests push, pull, and checkpoint functions.
 * These functions handle data transfer between machines and state preservation.
 *
 * Functions tested:
 * - backup_push (push repository to remote machine or storage)
 * - backup_pull (pull repository from remote machine or storage)
 * - checkpoint_create
 * - checkpoint_restore
 *
 * Note: checkpoint_list, checkpoint_info, checkpoint_delete are not implemented in Go.
 * Available checkpoint functions: checkpoint_create, checkpoint_restore, checkpoint_validate, checkpoint_cleanup, checkpoint_check_compat
 *
 * VMs are automatically started via global-setup.ts.
 */
test.describe('Backup Operations @bridge', () => {
  let runner: RenetFunctionsTestRunner;
  let testRepo: string;

  test.beforeAll(async () => {
    runner = RenetFunctionsTestRunner.forWorker();
    testRepo = await licensedRepository(runner);
  });

  test('push should not have shell syntax errors', async () => {
    const result = await runner.push(testRepo, runner.getWorkerVM2(), DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });

  test('pull should not have shell syntax errors', async () => {
    const result = await runner.pull(testRepo, runner.getWorkerVM(), DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });
});

test.describe('Checkpoint Operations @bridge', () => {
  let runner: RenetFunctionsTestRunner;
  let testRepo: string;
  const checkpointName = `ckpt-${Date.now()}`;

  test.beforeAll(async () => {
    runner = RenetFunctionsTestRunner.forWorker();
    testRepo = await licensedRepository(runner);
  });

  test('checkpoint_create should not have shell syntax errors', async () => {
    const result = await runner.checkpointCreate(testRepo, checkpointName, DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });

  test('checkpoint_restore should not have shell syntax errors', async () => {
    const result = await runner.checkpointRestore(testRepo, checkpointName, DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });
});

/**
 * Checkpoint Lifecycle Tests
 *
 * Tests the checkpoint create/restore lifecycle.
 * Note: checkpoint_list, checkpoint_info, checkpoint_delete are not implemented in Go.
 */
test.describe
  .serial('Checkpoint Lifecycle @bridge @lifecycle', () => {
    let runner: RenetFunctionsTestRunner;
    let repositoryName: string;
    const checkpoint1 = `ckpt1-${Date.now()}`;
    const checkpoint2 = `ckpt2-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      repositoryName = await licensedRepository(runner);
    });

    test('1. checkpoint_create: create first checkpoint', async () => {
      const result = await runner.checkpointCreate(repositoryName, checkpoint1, datastorePath);
      expectRan(runner, result);
    });

    test('2. checkpoint_create: create second checkpoint', async () => {
      const result = await runner.checkpointCreate(repositoryName, checkpoint2, datastorePath);
      expectRan(runner, result);
    });

    test('3. checkpoint_restore: restore to checkpoint1', async () => {
      const result = await runner.checkpointRestore(repositoryName, checkpoint1, datastorePath);
      expectRan(runner, result);
    });
  });

/**
 * Backup/Checkpoint Error Handling Tests
 *
 * Tests error handling for backup and checkpoint operations.
 */
test.describe('Backup/Checkpoint Error Handling @bridge', () => {
  let runner: RenetFunctionsTestRunner;
  let repo: string;

  test.beforeAll(async () => {
    runner = RenetFunctionsTestRunner.forWorker();
    repo = await licensedRepository(runner);
  });

  test('push to unreachable machine should handle gracefully', async () => {
    const result = await runner.push(repo, '10.0.0.254', DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });

  test('pull from unreachable machine should handle gracefully', async () => {
    const result = await runner.pull(repo, '10.0.0.254', DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });

  test('restore nonexistent checkpoint should handle gracefully', async () => {
    const result = await runner.checkpointRestore(repo, 'nonexistent-ckpt', DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });
});

/**
 * Push/Pull Multi-Machine Tests
 *
 * Tests data transfer between multiple machines.
 * VMs are automatically started via global-setup.ts.
 */
test.describe('Multi-Machine Backup Operations @bridge @multi-machine', () => {
  let runner: RenetFunctionsTestRunner;
  let repositoryName: string;

  test.beforeAll(async () => {
    runner = RenetFunctionsTestRunner.forWorker();
    repositoryName = await licensedRepository(runner);
  });

  test('push from VM1 to VM2', async () => {
    const result = await runner.push(repositoryName, runner.getWorkerVM2(), DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });

  test('pull from VM1 to VM2', async () => {
    const result = await runner.pull(repositoryName, runner.getWorkerVM(), DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });
});

/**
 * Checkpoint Naming Tests
 *
 * Tests various checkpoint name formats.
 */
test.describe('Checkpoint Naming @bridge', () => {
  let runner: RenetFunctionsTestRunner;
  let repositoryName: string;

  test.beforeAll(async () => {
    runner = RenetFunctionsTestRunner.forWorker();
    repositoryName = await licensedRepository(runner);
  });

  test('checkpoint with timestamp name should work', async () => {
    const name = `ckpt-${new Date().toISOString().replaceAll(/[:.]/g, '-')}`;
    const result = await runner.checkpointCreate(repositoryName, name, DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });

  test('checkpoint with simple name should work', async () => {
    const result = await runner.checkpointCreate(
      repositoryName,
      'daily-backup',
      DEFAULT_DATASTORE_PATH
    );
    expectRan(runner, result);
  });

  test('checkpoint with version name should work', async () => {
    const result = await runner.checkpointCreate(repositoryName, 'v1.0.0', DEFAULT_DATASTORE_PATH);
    expectRan(runner, result);
  });

  test('checkpoint with underscores should work', async () => {
    const result = await runner.checkpointCreate(
      repositoryName,
      'pre_release_v2',
      DEFAULT_DATASTORE_PATH
    );
    expectRan(runner, result);
  });
});

/**
 * Backup Push - Multi-Machine Options Tests
 *
 * Tests push to different machines using the destMachine parameter.
 * Note: Advanced parameters (destinationType, tag, state, checkpoint, etc.)
 * are passed via vault when queuing tasks, not as CLI flags in test mode.
 * Full parameter testing requires the queue API integration.
 */
test.describe('Backup Push - Machine Options @bridge', () => {
  let runner: RenetFunctionsTestRunner;
  let testRepo: string;

  test.beforeAll(async () => {
    runner = RenetFunctionsTestRunner.forWorker();
    testRepo = await licensedRepository(runner);
  });

  test('push to worker2 should have valid syntax', async () => {
    const result = await runner.pushWithOptions(testRepo, {
      destMachine: runner.getWorkerVM2(),
      datastorePath: DEFAULT_DATASTORE_PATH,
    });
    expectRan(runner, result);
  });

  test('push to worker1 should have valid syntax', async () => {
    const result = await runner.pushWithOptions(testRepo, {
      destMachine: runner.getWorkerVM(),
      datastorePath: DEFAULT_DATASTORE_PATH,
    });
    expectRan(runner, result);
  });
});

/**
 * Backup Pull - Machine Options Tests
 *
 * Tests pull from different machines using the sourceMachine parameter.
 * Note: Advanced parameters (sourceType, from, grand, etc.)
 * are passed via vault when queuing tasks, not as CLI flags in test mode.
 */
test.describe('Backup Pull - Machine Options @bridge', () => {
  let runner: RenetFunctionsTestRunner;
  let testRepo: string;

  test.beforeAll(async () => {
    runner = RenetFunctionsTestRunner.forWorker();
    testRepo = await licensedRepository(runner);
  });

  test('pull from worker1 should have valid syntax', async () => {
    const result = await runner.pullWithOptions(testRepo, {
      sourceMachine: runner.getWorkerVM(),
      datastorePath: DEFAULT_DATASTORE_PATH,
    });
    expectRan(runner, result);
  });

  test('pull from worker2 should have valid syntax', async () => {
    const result = await runner.pullWithOptions(testRepo, {
      sourceMachine: runner.getWorkerVM2(),
      datastorePath: DEFAULT_DATASTORE_PATH,
    });
    expectRan(runner, result);
  });
});
