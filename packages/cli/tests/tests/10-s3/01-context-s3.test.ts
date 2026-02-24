/**
 * Playwright CLI tests for S3 config commands.
 *
 * Exercises `config init` (with S3 flags), `config show`, `config add-machine`,
 * and `config list` against a real RustFS server.
 *
 * Tests both encrypted (with master password) and plaintext (without) modes.
 *
 * Requires S3_TEST_ENDPOINT, S3_TEST_ACCESS_KEY, S3_TEST_SECRET_KEY, S3_TEST_BUCKET.
 */

import { expect, test } from '@playwright/test';
import { DEFAULTS } from '@rediacc/shared/config';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import {
  type S3TestEnv,
  generateS3ContextName,
  getS3TestEnv,
  hasS3TestEnv,
} from '../../src/utils/s3';

// Defer env var access — calling getS3TestEnv() at module level crashes
// Playwright's test discovery when S3_TEST_* vars aren't set.
const s3Available = hasS3TestEnv();
const s3Env: S3TestEnv = s3Available
  ? getS3TestEnv()
  : { endpoint: '', accessKeyId: '', secretAccessKey: '', bucket: '' };
const sshKeyPath = process.env.E2E_SSH_KEY ?? DEFAULTS.CLI_TEST.SSH_KEY_PATH;

// --- Encrypted mode (with master password) ---

const encContextName = generateS3ContextName('ctx-s3-enc');
const encMasterPassword = `test-master-pw-${Date.now()}`;
const encPrefix = `pw-ctx-enc-${Date.now()}`;

test.describe('S3 Config Commands (with master password) @cli @s3', () => {
  test.skip(!s3Available, 'S3_TEST_* environment variables not set');
  const runner = new CliTestRunner();

  test.afterAll(async () => {
    try {
      await runner.run(['config', 'delete', encContextName]);
    } catch {
      // Ignore errors during cleanup
    }
  });

  test('should create an S3 config with master password', async () => {
    const result = await runner.run(
      [
        'config',
        'init',
        encContextName,
        '--s3-endpoint',
        s3Env.endpoint,
        '--s3-bucket',
        s3Env.bucket,
        '--s3-access-key-id',
        s3Env.accessKeyId,
        '--s3-secret-access-key',
        s3Env.secretAccessKey,
        '--ssh-key',
        sshKeyPath,
        '--s3-region',
        'us-east-1',
        '--s3-prefix',
        encPrefix,
        '--master-password',
        encMasterPassword,
      ],
      { skipJsonParse: true }
    );

    runner.expectSuccess(result);
    const output = result.stdout + result.stderr;
    expect(output).toContain('S3 access verified');
    expect(output).toContain(`"${encContextName}" initialized`);
  });

  test('should show S3 config details (adapter=local, s3State=yes)', async () => {
    const ctxRunner = new CliTestRunner({
      context: encContextName,
      credentials: { email: '', password: '', masterPassword: encMasterPassword },
    });
    const result = await ctxRunner.run(['config', 'show']);

    runner.expectSuccess(result);
    const data = runner.expectSuccessObject<Record<string, unknown>>(result);
    expect(data.adapter).toBe('local');
    expect(data.s3State).toBe('yes');
    expect(data.endpoint).toBe(s3Env.endpoint);
    expect(data.bucket).toBe(s3Env.bucket);
    expect(data.prefix).toBe(encPrefix);
  });

  test('should add a machine to S3 config', async () => {
    const ctxRunner = new CliTestRunner({
      context: encContextName,
      credentials: { email: '', password: '', masterPassword: encMasterPassword },
    });
    const result = await ctxRunner.run(
      ['config', 'add-machine', 'test-vm', '--ip', '192.168.1.100', '--user', 'root'],
      { skipJsonParse: true }
    );

    runner.expectSuccess(result);
  });

  test('should list configs and show local adapter for S3', async () => {
    const result = await runner.run(['config', 'list']);
    runner.expectSuccess(result);

    const contexts = runner.expectSuccessArray<Record<string, string>>(result);
    const s3Context = contexts.find((c) => c.name === encContextName);
    expect(s3Context).toBeDefined();
    expect(s3Context!.adapter).toBe('local');
  });

  test('should reject init with invalid S3 endpoint', async () => {
    const badName = generateS3ContextName('bad-s3');
    const result = await runner.run(
      [
        'config',
        'init',
        badName,
        '--s3-endpoint',
        'http://127.0.0.1:19999',
        '--s3-bucket',
        'nonexistent',
        '--s3-access-key-id',
        'fake',
        '--s3-secret-access-key',
        'fake',
        '--ssh-key',
        sshKeyPath,
        '--master-password',
        'pw',
      ],
      { skipJsonParse: true, timeout: 15000 }
    );

    expect(result.exitCode).not.toBe(0);
  });

  test('should show machines after adding one', async () => {
    const ctxRunner = new CliTestRunner({
      context: encContextName,
      credentials: { email: '', password: '', masterPassword: encMasterPassword },
    });
    const result = await ctxRunner.run(['config', 'machines']);

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

test.describe('S3 Config Commands (without master password) @cli @s3', () => {
  test.skip(!s3Available, 'S3_TEST_* environment variables not set');
  const runner = new CliTestRunner();

  test.afterAll(async () => {
    try {
      await runner.run(['config', 'delete', ptContextName]);
    } catch {
      // Ignore errors during cleanup
    }
  });

  test('should create an S3 config without master password', async () => {
    const result = await runner.run(
      [
        'config',
        'init',
        ptContextName,
        '--s3-endpoint',
        s3Env.endpoint,
        '--s3-bucket',
        s3Env.bucket,
        '--s3-access-key-id',
        s3Env.accessKeyId,
        '--s3-secret-access-key',
        s3Env.secretAccessKey,
        '--ssh-key',
        sshKeyPath,
        '--s3-region',
        'us-east-1',
        '--s3-prefix',
        ptPrefix,
      ],
      { skipJsonParse: true }
    );

    runner.expectSuccess(result);
    const output = result.stdout + result.stderr;
    expect(output).toContain('S3 access verified');
    expect(output).toContain(`"${ptContextName}" initialized`);
  });

  test('should show S3 config details without master password', async () => {
    const ctxRunner = CliTestRunner.withContext(ptContextName);
    const result = await ctxRunner.run(['config', 'show']);

    runner.expectSuccess(result);
    const data = runner.expectSuccessObject<Record<string, unknown>>(result);
    expect(data.adapter).toBe('local');
    expect(data.s3State).toBe('yes');
    expect(data.endpoint).toBe(s3Env.endpoint);
    expect(data.bucket).toBe(s3Env.bucket);
    expect(data.prefix).toBe(ptPrefix);
  });

  test('should add a machine to S3 config without master password', async () => {
    const ctxRunner = CliTestRunner.withContext(ptContextName);
    const result = await ctxRunner.run(
      ['config', 'add-machine', 'test-vm', '--ip', '192.168.1.150', '--user', 'root'],
      { skipJsonParse: true }
    );

    runner.expectSuccess(result);
  });

  test('should show machines in plaintext config', async () => {
    const ctxRunner = CliTestRunner.withContext(ptContextName);
    const result = await ctxRunner.run(['config', 'machines']);

    runner.expectSuccess(result);
    const machines = runner.expectSuccessArray<Record<string, unknown>>(result);
    const vm = machines.find((m) => m.name === 'test-vm');
    expect(vm).toBeDefined();
    expect(vm!.ip).toBe('192.168.1.150');
    expect(vm!.user).toBe('root');
  });
});
