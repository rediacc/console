import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import { describe, expect, it } from 'vitest';
import { buildPasswordVault } from '../renet-functions/passwordVault';
import { feedStdin } from '../renet-functions/stdinFeed';

const execAsync = promisify(exec);

describe('feedStdin', () => {
  it('delivers the text to the child and closes stdin', async () => {
    const pending = execAsync('cat');
    feedStdin(pending.child.stdin, 'hunter2\n');
    const { stdout } = await pending;
    expect(stdout).toBe('hunter2\n');
  });

  it('survives a child that exits before reading (EPIPE is not an unhandled error)', async () => {
    const unhandled: unknown[] = [];
    const onUnhandled = (error: unknown) => unhandled.push(error);
    process.on('uncaughtException', onUnhandled);
    try {
      const pending = execAsync('true');
      feedStdin(pending.child.stdin, 'x'.repeat(4 * 1024 * 1024));
      await pending;
      await new Promise((resolve) => setTimeout(resolve, 50));
    } finally {
      process.off('uncaughtException', onUnhandled);
    }
    expect(unhandled).toEqual([]);
  });

  it('is a no-op without a stdin stream', () => {
    expect(() => feedStdin(null, 'secret')).not.toThrow();
  });
});

describe('buildPasswordVault', () => {
  const opts = {
    function: 'repository_create',
    repository: 'r1',
    password: 'p@ss word',
    size: '1G',
    datastorePath: '/mnt/ds',
  };

  it('carries the credential, network id, size and datastore the flags carried', () => {
    const vault = JSON.parse(buildPasswordVault(opts, '2816'));
    expect(vault.task.function).toBe('repository_create');
    expect(vault.repository_credentials).toEqual({ r1: 'p@ss word' });
    expect(vault.repositories.r1.network_id).toBe(2816);
    expect(vault.params).toMatchObject({
      network_id: 2816,
      size: '1G',
      datastore_path: '/mnt/ds',
    });
    expect(vault.machine.datastore).toBe('/mnt/ds');
  });

  it('prefers an explicit network id and maps newSize', () => {
    const vault = JSON.parse(
      buildPasswordVault({ ...opts, networkId: '3000', newSize: '2G' }, '2816')
    );
    expect(vault.params.network_id).toBe(3000);
    expect(vault.params.new_size).toBe('2G');
  });

  it('refuses an option the vault does not carry rather than dropping it', () => {
    expect(() => buildPasswordVault({ ...opts, pool: 'p' }, '2816')).toThrow(/pool/);
  });
});
