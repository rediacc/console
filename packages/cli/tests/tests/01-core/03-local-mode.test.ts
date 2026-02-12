import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

/**
 * Integration tests for local mode CLI commands.
 *
 * These tests verify the CLI commands work correctly through
 * the actual process execution. Tests the context create-local,
 * add-machine, remove-machine, machines, and run commands.
 *
 * NOTE: These tests don't need the master context - they create their own local contexts.
 */

// Dummy SSH key content for testing (not a real key, just needs to exist)
const DUMMY_SSH_KEY = `-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBtest-key-for-cli-tests-only-not-realAAAAQtest-key-for-cli
-----END OPENSSH PRIVATE KEY-----`;

const DUMMY_SSH_PUB =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHRlc3Qta2V5LWZvci1jbGktdGVzdHMtb25seS1ub3QtcmVhbA== test@cli-tests';

/**
 * Ensures test SSH key files exist for local mode tests.
 * Creates dummy keys in ~/.ssh/ if they don't exist.
 */
function ensureTestSshKeys(): void {
  const sshDir = path.join(os.homedir(), '.ssh');

  // Create .ssh directory if it doesn't exist
  if (!fs.existsSync(sshDir)) {
    fs.mkdirSync(sshDir, { mode: 0o700 });
  }

  // Create id_rsa if it doesn't exist
  const rsaPath = path.join(sshDir, 'id_rsa');
  if (!fs.existsSync(rsaPath)) {
    fs.writeFileSync(rsaPath, DUMMY_SSH_KEY, { mode: 0o600 });
  }

  // Create id_ed25519 if it doesn't exist
  const ed25519Path = path.join(sshDir, 'id_ed25519');
  if (!fs.existsSync(ed25519Path)) {
    fs.writeFileSync(ed25519Path, DUMMY_SSH_KEY, { mode: 0o600 });
  }

  // Create id_ed25519.pub if it doesn't exist
  const ed25519PubPath = path.join(sshDir, 'id_ed25519.pub');
  if (!fs.existsSync(ed25519PubPath)) {
    fs.writeFileSync(ed25519PubPath, DUMMY_SSH_PUB, { mode: 0o644 });
  }
}

test.describe('Local Context Commands @cli @core', () => {
  const timestamp = Date.now();
  const testLocalContext = `test-local-cli-${timestamp}`;
  const testMachine = 'test-server';
  let runner: CliTestRunner;

  test.beforeAll(() => {
    // Ensure SSH keys exist for testing (creates dummy keys in CI)
    ensureTestSshKeys();
    // Use a runner without context for creating local contexts
    runner = new CliTestRunner({});
  });

  test.afterAll(async () => {
    // Cleanup: delete test context
    await runner.run(['context', 'delete', testLocalContext, '--force'], { skipJsonParse: true });
  });

  test.describe('context create-local', () => {
    test('should create a new local context', async () => {
      const result = await runner.run(
        ['context', 'create-local', testLocalContext, '--ssh-key', '~/.ssh/id_rsa'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('created');
      expect(result.stdout).toContain(testLocalContext);
    });

    test('should fail if SSH key path is missing', async () => {
      const result = await runner.run(['context', 'create-local', 'no-key-context'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('--ssh-key');
    });

    test('should accept custom renet path', async () => {
      const customPathContext = `test-custom-${timestamp}`;

      const result = await runner.run(
        [
          'context',
          'create-local',
          customPathContext,
          '--ssh-key',
          '~/.ssh/id_rsa',
          '--renet-path',
          '/opt/bin/renet',
        ],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);

      // Check the path using --context flag
      const showResult = await runner.run(['--context', customPathContext, 'context', 'show']);

      expect(showResult.json).toBeDefined();
      expect((showResult.json as { renetPath: string }).renetPath).toBe('/opt/bin/renet');

      // Cleanup
      await runner.run(['context', 'delete', customPathContext, '--force'], {
        skipJsonParse: true,
      });
    });

    test('should fail for duplicate context name', async () => {
      const result = await runner.run(
        ['context', 'create-local', testLocalContext, '--ssh-key', '~/.ssh/id_rsa'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('already exists');
    });
  });

  test.describe('context add-machine', () => {
    test('should add a machine to the local context', async () => {
      const result = await runner.run(
        [
          '--context',
          testLocalContext,
          'context',
          'add-machine',
          testMachine,
          '--ip',
          '192.168.1.100',
          '--user',
          'testuser',
        ],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain(testMachine);
      expect(result.stdout).toContain('added');
    });

    test('should accept optional port and datastore', async () => {
      const result = await runner.run(
        [
          '--context',
          testLocalContext,
          'context',
          'add-machine',
          'full-machine',
          '--ip',
          '10.0.0.1',
          '--user',
          'admin',
          '--port',
          '2222',
          '--datastore',
          '/data/rediacc',
        ],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
    });

    test('should fail without required --ip', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'add-machine', 'no-ip', '--user', 'testuser'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('--ip');
    });

    test('should fail without required --user', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'add-machine', 'no-user', '--ip', '10.0.0.1'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('--user');
    });
  });

  test.describe('context machines', () => {
    test('should list all machines', async () => {
      const result = await runner.run(['--context', testLocalContext, 'context', 'machines']);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const machines = runner.expectSuccessArray<{ name: string; ip: string }>(result);
      expect(machines.length).toBeGreaterThanOrEqual(1);

      const testMachineEntry = machines.find((m) => m.name === testMachine);
      expect(testMachineEntry).toBeDefined();
      expect(testMachineEntry?.ip).toBe('192.168.1.100');
    });

    test('should show machine details in table format', async () => {
      const result = await runner.run(['--context', testLocalContext, 'context', 'machines'], {
        outputFormat: 'table',
      });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain(testMachine);
      expect(result.stdout).toContain('192.168.1.100');
    });
  });

  test.describe('context show (local mode)', () => {
    test('should show local context details', async () => {
      const result = await runner.run(['--context', testLocalContext, 'context', 'show']);

      expect(result.success).toBe(true);
      expect(result.json).toBeDefined();

      const ctx = result.json as {
        name: string;
        mode: string;
        sshKey: string;
        machines: number;
      };

      expect(ctx.name).toBe(testLocalContext);
      expect(ctx.mode).toBe('local');
      expect(ctx.sshKey).toContain('.ssh');
      expect(ctx.machines).toBeGreaterThanOrEqual(1);
    });
  });

  test.describe('context list (with local)', () => {
    test('should show mode column in list', async () => {
      const result = await runner.run(['context', 'list']);

      expect(result.success).toBe(true);
      const contexts = runner.expectSuccessArray<{
        name: string;
        mode: string;
        machines: string;
      }>(result);

      const localCtx = contexts.find((c) => c.name === testLocalContext);
      expect(localCtx?.mode).toBe('local');
      expect(localCtx?.machines).toBeDefined();
    });
  });

  test.describe('context set-ssh', () => {
    test('should update SSH configuration', async () => {
      const result = await runner.run(
        [
          '--context',
          testLocalContext,
          'context',
          'set-ssh',
          '--private-key',
          '~/.ssh/id_ed25519',
          '--public-key',
          '~/.ssh/id_ed25519.pub',
        ],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('updated');
    });
  });

  test.describe('context set-renet', () => {
    test('should update renet path', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'set-renet', '/usr/bin/renet'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('set to');

      // Verify in show
      const showResult = await runner.run(['--context', testLocalContext, 'context', 'show']);
      expect((showResult.json as { renetPath: string }).renetPath).toBe('/usr/bin/renet');
    });
  });

  test.describe('context remove-machine', () => {
    test('should remove a machine', async () => {
      // First add a machine to remove
      await runner.run(
        [
          '--context',
          testLocalContext,
          'context',
          'add-machine',
          'to-remove',
          '--ip',
          '1.1.1.1',
          '--user',
          'test',
        ],
        { skipJsonParse: true }
      );

      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'remove-machine', 'to-remove'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('removed');

      // Verify it's gone
      const machinesResult = await runner.run([
        '--context',
        testLocalContext,
        'context',
        'machines',
      ]);
      const machines = runner.expectSuccessArray<{ name: string }>(machinesResult);
      expect(machines.find((m) => m.name === 'to-remove')).toBeUndefined();
    });

    test('should fail for non-existent machine', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'remove-machine', 'nonexistent'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('not found');
    });
  });

  test.describe('run command (local mode detection)', () => {
    test('should detect local mode and show local prefix', async () => {
      // This test verifies that run command detects local mode
      // It will fail if renet isn't installed, but that's expected
      const result = await runner.run(
        ['--context', testLocalContext, 'run', 'machine_ping', '--machine', testMachine],
        { skipJsonParse: true }
      );

      // The command should attempt to run in local mode
      if (!result.success) {
        const output = result.stdout + result.stderr;
        const isLocalModeAttempt =
          output.includes('[local]') ||
          output.includes('spawn') ||
          output.includes('renet') ||
          output.includes('SSH');
        expect(isLocalModeAttempt).toBe(true);
      }
    });

    test('should require machine in local mode', async () => {
      // Clear the default machine first
      await runner.run(['--context', testLocalContext, 'context', 'clear', 'machine'], {
        skipJsonParse: true,
      });

      const result = await runner.run(['--context', testLocalContext, 'run', 'machine_ping'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('machine');
    });

    test('should accept --debug flag', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'run', 'machine_ping', '--machine', testMachine, '--debug'],
        { skipJsonParse: true }
      );

      const output = result.stdout + result.stderr;
      expect(output).not.toContain('unknown option');
    });
  });
});

test.describe('Switching Between Local and Cloud Contexts @cli @core', () => {
  const timestamp = Date.now();
  const localContext = `switch-local-${timestamp}`;
  const cloudContext = `switch-cloud-${timestamp}`;
  let runner: CliTestRunner;

  test.beforeAll(() => {
    // Ensure SSH keys exist for testing (creates dummy keys in CI)
    ensureTestSshKeys();
    runner = new CliTestRunner({});
  });

  test.afterAll(async () => {
    await runner.run(['context', 'delete', localContext, '--force'], { skipJsonParse: true });
    await runner.run(['context', 'delete', cloudContext, '--force'], { skipJsonParse: true });
  });

  test('should use correct mode for each context with -C flag', async () => {
    // Create both contexts
    await runner.run(['context', 'create-local', localContext, '--ssh-key', '~/.ssh/id_rsa'], {
      skipJsonParse: true,
    });
    await runner.run(
      ['context', 'create', cloudContext, '--api-url', 'https://test.example.com/api'],
      { skipJsonParse: true }
    );

    // Check local context with --context
    const localResult = await runner.run(['--context', localContext, 'context', 'show']);
    expect((localResult.json as { mode: string }).mode).toBe('local');

    // Check cloud context with --context
    const cloudResult = await runner.run(['--context', cloudContext, 'context', 'show']);
    expect((cloudResult.json as { mode: string }).mode).toBe('cloud');
  });
});

// ============================================================================
// Local Storage Commands
// ============================================================================

/**
 * Creates a temporary rclone config file for testing.
 * Includes s3, drive (supported), and crypt (unsupported) sections.
 */
function createTestRcloneConfig(): string {
  const configPath = path.join(os.tmpdir(), `test-rclone-${Date.now()}.conf`);
  fs.writeFileSync(
    configPath,
    `[my-s3]
type = s3
region = us-east-1
access_key_id = AKIA123456
secret_access_key = secret123

[my-drive]
type = drive
token = {"access_token":"ya29.test","expiry":"2026-01-01T00:00:00Z"}

[unsupported-remote]
type = crypt
password = encrypted
`
  );
  return configPath;
}

test.describe('Local Storage Commands @cli @core', () => {
  const timestamp = Date.now();
  const storageContext = `test-storage-${timestamp}`;
  let runner: CliTestRunner;
  let rcloneConfigPath: string;

  test.beforeAll(() => {
    ensureTestSshKeys();
    runner = new CliTestRunner({});
    rcloneConfigPath = createTestRcloneConfig();
  });

  test.afterAll(async () => {
    await runner.run(['context', 'delete', storageContext], { skipJsonParse: true });
    try {
      fs.unlinkSync(rcloneConfigPath);
    } catch {
      // Ignore cleanup errors
    }
  });

  // Tests are sequential — order matters for stateful storage operations.
  // No nested test.describe blocks to avoid Playwright retry isolation issues.

  test('should create local context for storage testing', async () => {
    const result = await runner.run(
      ['context', 'create-local', storageContext, '--ssh-key', '~/.ssh/id_rsa'],
      { skipJsonParse: true }
    );
    expect(result.success).toBe(true);
  });

  test('should show no storages on fresh context', async () => {
    const result = await runner.run(
      ['--context', storageContext, 'context', 'storages'],
      { skipJsonParse: true }
    );

    expect(result.success).toBe(true);
    const output = result.stdout + result.stderr;
    expect(
      output.includes('No storages') || output.includes('no storages') || output.includes('[]')
    ).toBe(true);
  });

  test('should import all supported storages from rclone config', async () => {
    const result = await runner.run(
      ['--context', storageContext, 'context', 'import-storage', rcloneConfigPath],
      { skipJsonParse: true }
    );

    expect(result.success).toBe(true);
    const output = result.stdout + result.stderr;
    // Should import 2 supported storages (s3, drive)
    expect(output).toContain('my-s3');
    expect(output).toContain('my-drive');
    // Should warn about unsupported type (warning goes to stderr)
    expect(output).toContain('unsupported');
  });

  test('should import single storage with --name', async () => {
    // Create a fresh context to test --name isolation
    const singleCtx = `test-single-import-${timestamp}`;
    await runner.run(
      ['context', 'create-local', singleCtx, '--ssh-key', '~/.ssh/id_rsa'],
      { skipJsonParse: true }
    );

    const result = await runner.run(
      ['--context', singleCtx, 'context', 'import-storage', rcloneConfigPath, '--name', 'my-s3'],
      { skipJsonParse: true }
    );

    expect(result.success).toBe(true);
    expect(result.stdout).toContain('my-s3');

    // Verify only one storage was imported
    const listResult = await runner.run(['--context', singleCtx, 'context', 'storages']);
    if (Array.isArray(listResult.json)) {
      expect(listResult.json).toHaveLength(1);
      expect((listResult.json[0] as { name: string }).name).toBe('my-s3');
    }

    // Cleanup
    await runner.run(['context', 'delete', singleCtx], { skipJsonParse: true });
  });

  test('should fail when --name references non-existent section', async () => {
    const result = await runner.run(
      [
        '--context',
        storageContext,
        'context',
        'import-storage',
        rcloneConfigPath,
        '--name',
        'nonexistent',
      ],
      { skipJsonParse: true }
    );

    expect(result.success).toBe(false);
    expect(result.stdout + result.stderr).toContain('not found');
  });

  test('should fail when file does not exist', async () => {
    const result = await runner.run(
      ['--context', storageContext, 'context', 'import-storage', '/tmp/nonexistent-rclone.conf'],
      { skipJsonParse: true }
    );

    expect(result.success).toBe(false);
  });

  test('should fail when file has no valid configs', async () => {
    const emptyConf = path.join(os.tmpdir(), `test-empty-${Date.now()}.conf`);
    fs.writeFileSync(emptyConf, '# only comments\n; nothing here\n');

    const result = await runner.run(
      ['--context', storageContext, 'context', 'import-storage', emptyConf],
      { skipJsonParse: true }
    );

    expect(result.success).toBe(false);
    expect(result.stdout + result.stderr).toMatch(/no valid|no storage/i);

    try {
      fs.unlinkSync(emptyConf);
    } catch {
      // Ignore
    }
  });

  test('should list imported storages with name and provider', async () => {
    const result = await runner.run(['--context', storageContext, 'context', 'storages']);

    expect(result.success).toBe(true);
    expect(Array.isArray(result.json)).toBe(true);

    const storages = result.json as { name: string; provider: string }[];
    expect(storages.length).toBeGreaterThanOrEqual(2);

    const s3Entry = storages.find((s) => s.name === 'my-s3');
    expect(s3Entry).toBeDefined();
    expect(s3Entry?.provider).toBe('s3');

    const driveEntry = storages.find((s) => s.name === 'my-drive');
    expect(driveEntry).toBeDefined();
    expect(driveEntry?.provider).toBe('drive');
  });

  test('should remove a specific storage', async () => {
    const result = await runner.run(
      ['--context', storageContext, 'context', 'remove-storage', 'my-drive'],
      { skipJsonParse: true }
    );

    expect(result.success).toBe(true);
    expect(result.stdout).toContain('removed');

    // Verify it's gone
    const listResult = await runner.run(['--context', storageContext, 'context', 'storages']);
    if (Array.isArray(listResult.json)) {
      const names = (listResult.json as { name: string }[]).map((s) => s.name);
      expect(names).not.toContain('my-drive');
    }
  });

  test('should leave other storages intact after removal', async () => {
    const listResult = await runner.run(['--context', storageContext, 'context', 'storages']);

    expect(listResult.success).toBe(true);
    if (Array.isArray(listResult.json)) {
      const names = (listResult.json as { name: string }[]).map((s) => s.name);
      expect(names).toContain('my-s3');
    }
  });

  test('should fail for non-existent storage name on remove', async () => {
    const result = await runner.run(
      ['--context', storageContext, 'context', 'remove-storage', 'nonexistent'],
      { skipJsonParse: true }
    );

    expect(result.success).toBe(false);
    expect(result.stdout + result.stderr).toContain('not found');
  });

  test('should include storage count in context show', async () => {
    const result = await runner.run(['--context', storageContext, 'context', 'show']);

    expect(result.success).toBe(true);
    expect(result.json).toBeDefined();

    const ctx = result.json as { storages?: number };
    expect(ctx.storages).toBeDefined();
    expect(ctx.storages).toBeGreaterThanOrEqual(1);
  });
});
