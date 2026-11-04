import { describe, expect, it } from 'vitest';

import { peerKnownHosts, peerKnownHostsArg } from '../peerKnownHosts';
import type { ExecResult } from '../types';

function runner(result: Partial<ExecResult>, seen: string[] = []) {
  return (command: string): Promise<ExecResult> => {
    seen.push(command);

    return Promise.resolve({ code: 0, stdout: '', stderr: '', ...result } as ExecResult);
  };
}

describe('peerKnownHosts', () => {
  it('scans the peer on the machine the command runs on and returns the flag value', async () => {
    const seen: string[] = [];

    await expect(
      peerKnownHosts(runner({ stdout: 'c2Nhbm5lZA==\n' }, seen), '10.0.0.9')
    ).resolves.toBe('c2Nhbm5lZA==');
    expect(seen).toEqual(['ssh-keyscan -T 5 10.0.0.9 2>/dev/null | base64 -w0']);
  });

  it('yields nothing for a scan that failed, so the verb gives its coded refusal', async () => {
    await expect(peerKnownHosts(runner({ code: 1, stdout: 'noise' }), '10.0.0.9')).resolves.toBe(
      ''
    );
  });

  it('builds the flag only around a value', async () => {
    await expect(
      peerKnownHostsArg(runner({ stdout: 'cGlu' }), 'dest-known-hosts', '10.0.0.9')
    ).resolves.toBe(' --dest-known-hosts cGlu');
    await expect(
      peerKnownHostsArg(runner({ stdout: '' }), 'src-known-hosts', '10.0.0.9')
    ).resolves.toBe('');
  });
});
