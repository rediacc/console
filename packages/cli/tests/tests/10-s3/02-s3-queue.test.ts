/**
 * Playwright CLI tests for S3 queue operations.
 *
 * Exercises queue create, list, cancel, delete commands
 * in S3 mode against a real RustFS server.
 *
 * Tests both encrypted (with master password) and plaintext (without) modes.
 *
 * Note: `queue trace` requires a task to exist in a known status directory.
 * Trace is covered in the Vitest integration tests (s3-queue.integration.test.ts).
 *
 * Requires S3_TEST_ENDPOINT, S3_TEST_ACCESS_KEY, S3_TEST_SECRET_KEY, S3_TEST_BUCKET.
 */

import { expect, test } from '@playwright/test';
import { DEFAULTS } from '@rediacc/shared/config';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { generateS3ContextName, getS3TestEnv, hasS3TestEnv } from '../../src/utils/s3';

// Defer env var access — calling getS3TestEnv() at module level crashes
// Playwright's test discovery when S3_TEST_* vars aren't set.
const s3Available = hasS3TestEnv();
const s3Env = s3Available ? getS3TestEnv() : ({ endpoint: '', accessKeyId: '', secretAccessKey: '', bucket: '' } as ReturnType<typeof getS3TestEnv>);
const sshKeyPath = process.env.E2E_SSH_KEY ?? DEFAULTS.CLI_TEST.SSH_KEY_PATH;

/** Extract a UUID from CLI output text */
function extractTaskId(output: string): string {
  const match = /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/.exec(output);
  if (!match) throw new Error(`No UUID found in output: ${output}`);
  return match[1];
}

// --- Encrypted mode (with master password) ---

const encContextName = generateS3ContextName('q-s3-enc');
const encMasterPassword = `test-queue-pw-${Date.now()}`;
const encPrefix = `pw-queue-enc-${Date.now()}`;

test.describe('S3 Queue Operations (with master password) @cli @s3', () => {
  test.skip(!s3Available, 'S3_TEST_* environment variables not set');
  let runner: CliTestRunner;

  test.beforeAll(async () => {
    const setupRunner = new CliTestRunner();
    const createResult = await setupRunner.run(
      [
        'context',
        'create-s3',
        encContextName,
        '--endpoint',
        s3Env.endpoint,
        '--bucket',
        s3Env.bucket,
        '--access-key-id',
        s3Env.accessKeyId,
        '--secret-access-key',
        s3Env.secretAccessKey,
        '--ssh-key',
        sshKeyPath,
        '--region',
        'us-east-1',
        '--prefix',
        encPrefix,
        '--master-password',
        encMasterPassword,
      ],
      { skipJsonParse: true }
    );
    setupRunner.expectSuccess(createResult);

    const ctxRunner = CliTestRunner.withContext(encContextName);
    const addResult = await ctxRunner.run(
      ['context', 'add-machine', 'test-vm', '--ip', '192.168.1.200', '--user', 'root'],
      { skipJsonParse: true }
    );
    ctxRunner.expectSuccess(addResult);

    runner = new CliTestRunner({
      context: encContextName,
      credentials: { email: '', password: '', masterPassword: encMasterPassword },
    });
  });

  test.afterAll(async () => {
    try {
      const cleanupRunner = new CliTestRunner();
      await cleanupRunner.run(['context', 'delete', encContextName]);
    } catch {
      // Ignore errors during cleanup
    }
  });

  test('should create a queue item', async () => {
    const result = await runner.run(
      [
        'queue',
        'create',
        '--function',
        'test_function',
        '--team',
        'default',
        '--machine',
        'test-vm',
        '--vault',
        '{}',
      ],
      { skipJsonParse: true }
    );

    runner.expectSuccess(result);
    const output = result.stdout + result.stderr;
    const taskId = extractTaskId(output);
    expect(taskId).toBeTruthy();
  });

  test('should list queue items', async () => {
    await runner.run(
      [
        'queue',
        'create',
        '--function',
        'list_test',
        '--team',
        'default',
        '--machine',
        'test-vm',
        '--vault',
        '{}',
      ],
      { skipJsonParse: true }
    );

    const result = await runner.run(['queue', 'list', '--team', 'default']);
    runner.expectSuccess(result);
  });

  test('should cancel a queue item', async () => {
    const createResult = await runner.run(
      [
        'queue',
        'create',
        '--function',
        'cancel_me',
        '--team',
        'default',
        '--machine',
        'test-vm',
        '--vault',
        '{}',
      ],
      { skipJsonParse: true }
    );
    runner.expectSuccess(createResult);
    const taskId = extractTaskId(createResult.stdout + createResult.stderr);

    const result = await runner.run(['queue', 'cancel', taskId], { skipJsonParse: true });
    runner.expectSuccess(result);
  });

  test('should delete a queue item', async () => {
    const createResult = await runner.run(
      [
        'queue',
        'create',
        '--function',
        'delete_me',
        '--team',
        'default',
        '--machine',
        'test-vm',
        '--vault',
        '{}',
      ],
      { skipJsonParse: true }
    );
    runner.expectSuccess(createResult);
    const taskId = extractTaskId(createResult.stdout + createResult.stderr);

    const deleteResult = await runner.run(['queue', 'delete', taskId, '--force'], {
      skipJsonParse: true,
    });
    runner.expectSuccess(deleteResult);
  });
});

// --- Plaintext mode (without master password) ---

const ptContextName = generateS3ContextName('q-s3-pt');
const ptPrefix = `pw-queue-pt-${Date.now()}`;

test.describe('S3 Queue Operations (without master password) @cli @s3', () => {
  test.skip(!s3Available, 'S3_TEST_* environment variables not set');
  let runner: CliTestRunner;

  test.beforeAll(async () => {
    const setupRunner = new CliTestRunner();
    const createResult = await setupRunner.run(
      [
        'context',
        'create-s3',
        ptContextName,
        '--endpoint',
        s3Env.endpoint,
        '--bucket',
        s3Env.bucket,
        '--access-key-id',
        s3Env.accessKeyId,
        '--secret-access-key',
        s3Env.secretAccessKey,
        '--ssh-key',
        sshKeyPath,
        '--region',
        'us-east-1',
        '--prefix',
        ptPrefix,
      ],
      { skipJsonParse: true }
    );
    setupRunner.expectSuccess(createResult);

    const ctxRunner = CliTestRunner.withContext(ptContextName);
    const addResult = await ctxRunner.run(
      ['context', 'add-machine', 'test-vm', '--ip', '192.168.1.201', '--user', 'root'],
      { skipJsonParse: true }
    );
    ctxRunner.expectSuccess(addResult);

    // No master password needed — plaintext mode
    runner = CliTestRunner.withContext(ptContextName);
  });

  test.afterAll(async () => {
    try {
      const cleanupRunner = new CliTestRunner();
      await cleanupRunner.run(['context', 'delete', ptContextName]);
    } catch {
      // Ignore errors during cleanup
    }
  });

  test('should create a queue item without encryption', async () => {
    const result = await runner.run(
      [
        'queue',
        'create',
        '--function',
        'test_plain',
        '--team',
        'default',
        '--machine',
        'test-vm',
        '--vault',
        '{}',
      ],
      { skipJsonParse: true }
    );

    runner.expectSuccess(result);
    const output = result.stdout + result.stderr;
    const taskId = extractTaskId(output);
    expect(taskId).toBeTruthy();
  });

  test('should list queue items without encryption', async () => {
    await runner.run(
      [
        'queue',
        'create',
        '--function',
        'list_plain',
        '--team',
        'default',
        '--machine',
        'test-vm',
        '--vault',
        '{}',
      ],
      { skipJsonParse: true }
    );

    const result = await runner.run(['queue', 'list', '--team', 'default']);
    runner.expectSuccess(result);
  });
});
