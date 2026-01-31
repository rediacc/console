/**
 * Playwright CLI tests for S3 context commands.
 *
 * Exercises `context create-s3`, `context show`, `context add-machine`,
 * and `context list` against a real RustFS server.
 *
 * Tests both encrypted (with master password) and plaintext (without) modes.
 *
 * Requires S3_TEST_ENDPOINT, S3_TEST_ACCESS_KEY, S3_TEST_SECRET_KEY, S3_TEST_BUCKET.
 */

import { expect, test } from '@playwright/test';
import { DEFAULTS } from '@rediacc/shared/config';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { generateS3ContextName, getS3TestEnv } from '../../src/utils/s3';

const s3Env = getS3TestEnv();
const sshKeyPath = process.env.E2E_SSH_KEY ?? DEFAULTS.CLI_TEST.SSH_KEY_PATH;

// --- Encrypted mode (with master password) ---

const encContextName = generateS3ContextName('ctx-s3-enc');
const encMasterPassword = `test-master-pw-${Date.now()}`;
const encPrefix = `pw-ctx-enc-${Date.now()}`;

test.describe('S3 Context Commands (with master password) @cli @s3', () => {
  const runner = new CliTestRunner();

  test.afterAll(async () => {
    try {
      await runner.run(['context', 'delete', encContextName]);
    } catch {
      // Ignore errors during cleanup
    }
  });

  test('should create an S3 context with master password', async () => {
    const result = await runner.run([
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
    ], { skipJsonParse: true });

    runner.expectSuccess(result);
    const output = result.stdout + result.stderr;
    expect(output).toContain('S3 access verified');
    expect(output).toContain(`S3 context "${encContextName}" created`);
  });

  test('should show S3 context details (mode=s3, endpoint, bucket)', async () => {
    const ctxRunner = CliTestRunner.withContext(encContextName);
    const result = await ctxRunner.run(['context', 'show']);

    runner.expectSuccess(result);
    const data = runner.expectSuccessObject<Record<string, unknown>>(result);
    expect(data.mode).toBe('s3');
    expect(data.endpoint).toBe(s3Env.endpoint);
    expect(data.bucket).toBe(s3Env.bucket);
    expect(data.prefix).toBe(encPrefix);
  });

  test('should add a machine to S3 context', async () => {
    const ctxRunner = CliTestRunner.withContext(encContextName);
    const result = await ctxRunner.run([
      'context',
      'add-machine',
      'test-vm',
      '--ip',
      '192.168.1.100',
      '--user',
      'root',
    ], { skipJsonParse: true });

    runner.expectSuccess(result);
  });

  test('should list contexts and show S3 mode', async () => {
    const result = await runner.run(['context', 'list']);
    runner.expectSuccess(result);

    const contexts = runner.expectSuccessArray<Record<string, string>>(result);
    const s3Context = contexts.find((c) => c.name === encContextName);
    expect(s3Context).toBeDefined();
    expect(s3Context!.mode).toBe('s3');
  });

  test('should reject create-s3 with invalid endpoint', async () => {
    const badName = generateS3ContextName('bad-s3');
    const result = await runner.run([
      'context',
      'create-s3',
      badName,
      '--endpoint',
      'http://127.0.0.1:19999',
      '--bucket',
      'nonexistent',
      '--access-key-id',
      'fake',
      '--secret-access-key',
      'fake',
      '--ssh-key',
      sshKeyPath,
      '--master-password',
      'pw',
    ], { skipJsonParse: true, timeout: 15000 });

    expect(result.exitCode).not.toBe(0);
  });

  test('should show machines after adding one', async () => {
    const ctxRunner = CliTestRunner.withContext(encContextName);
    const result = await ctxRunner.run(['context', 'machines']);

    runner.expectSuccess(result);
    const machines = runner.expectSuccessArray<Record<string, unknown>>(result);
    const vm = machines.find((m) => m.name === 'test-vm');
    expect(vm).toBeDefined();
    expect(vm!.ip).toBe('192.168.1.100');
    expect(vm!.user).toBe('root');
  });
});

// --- Plaintext mode (without master password) ---

const ptContextName = generateS3ContextName('ctx-s3-pt');
const ptPrefix = `pw-ctx-pt-${Date.now()}`;

test.describe('S3 Context Commands (without master password) @cli @s3', () => {
  const runner = new CliTestRunner();

  test.afterAll(async () => {
    try {
      await runner.run(['context', 'delete', ptContextName]);
    } catch {
      // Ignore errors during cleanup
    }
  });

  test('should create an S3 context without master password', async () => {
    const result = await runner.run([
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
    ], { skipJsonParse: true });

    runner.expectSuccess(result);
    const output = result.stdout + result.stderr;
    expect(output).toContain('S3 access verified');
    expect(output).toContain(`S3 context "${ptContextName}" created`);
  });

  test('should show S3 context details without master password', async () => {
    const ctxRunner = CliTestRunner.withContext(ptContextName);
    const result = await ctxRunner.run(['context', 'show']);

    runner.expectSuccess(result);
    const data = runner.expectSuccessObject<Record<string, unknown>>(result);
    expect(data.mode).toBe('s3');
    expect(data.endpoint).toBe(s3Env.endpoint);
    expect(data.bucket).toBe(s3Env.bucket);
    expect(data.prefix).toBe(ptPrefix);
  });

  test('should add a machine to S3 context without master password', async () => {
    const ctxRunner = CliTestRunner.withContext(ptContextName);
    const result = await ctxRunner.run([
      'context',
      'add-machine',
      'test-vm',
      '--ip',
      '192.168.1.150',
      '--user',
      'root',
    ], { skipJsonParse: true });

    runner.expectSuccess(result);
  });

  test('should show machines in plaintext context', async () => {
    const ctxRunner = CliTestRunner.withContext(ptContextName);
    const result = await ctxRunner.run(['context', 'machines']);

    runner.expectSuccess(result);
    const machines = runner.expectSuccessArray<Record<string, unknown>>(result);
    const vm = machines.find((m) => m.name === 'test-vm');
    expect(vm).toBeDefined();
    expect(vm!.ip).toBe('192.168.1.150');
    expect(vm!.user).toBe('root');
  });
});
