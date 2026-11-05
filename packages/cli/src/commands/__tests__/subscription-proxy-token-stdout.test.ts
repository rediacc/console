/**
 * `REDIACC_TOKEN=$(rdc subscription proxy-token)` captures stdout, and inside `$(...)` stdout is no
 * TTY, so the root hook resolves the output format to JSON. With the real error handler, a refusal
 * must still leave stdout empty: on bench (2026-11-05) the JSON error envelope landed there, the
 * substitution captured it as a token, and the next call failed with
 * "Headers.append: invalid header value".
 */

import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { fakeAccountServer } = vi.hoisted(() => ({ fakeAccountServer: vi.fn() }));

class ExitCalled extends Error {
  constructor(readonly code: number) {
    super(`exit ${code}`);
  }
}

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: fakeAccountServer,
}));
vi.mock('../../services/account/subscription-auth.js', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../services/account/subscription-auth.js')>();
  return {
    getSubscriptionScopeMismatch: real.getSubscriptionScopeMismatch,
    getSubscriptionTokenState: () => ({
      kind: 'ready',
      token: { token: 'rdt_login', serverUrl: 'https://eu.example.test', teamName: 'Default' },
      serverUrl: 'https://eu.example.test',
    }),
  };
});
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getTeam: async () => 'Default' },
}));
vi.mock('../../services/core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/core/request-context.js')>()),
  exitProcess: (code: number) => {
    throw new ExitCalled(code);
  },
}));

import { setOutputFormat } from '../../utils/errors.js';

let stdout: string[];
let stderr: string[];

beforeEach(() => {
  vi.clearAllMocks();
  stdout = [];
  stderr = [];
  vi.spyOn(process.stdout, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stdout.push(String(chunk));
    return true;
  });
  vi.spyOn(process.stderr, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stderr.push(String(chunk));
    return true;
  });
  vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
    stderr.push(`${args.join(' ')}\n`);
  });
});

afterEach(() => {
  setOutputFormat('table');
  vi.restoreAllMocks();
});

describe('rdc subscription proxy-token inside $(...)', () => {
  it('writes a refusal to stderr and nothing to stdout, even when the run resolved to JSON', async () => {
    // What the root preAction does when stdout is a pipe.
    setOutputFormat('json');
    fakeAccountServer.mockRejectedValueOnce(
      Object.assign(new Error('A proxy token cannot mint another proxy token.'), { status: 403 })
    );
    const { registerSubscriptionCommands } = await import('../subscription.js');
    const program = new Command().exitOverride();
    registerSubscriptionCommands(program);

    const outcome = await program
      .parseAsync(['node', 'rdc', 'subscription', 'proxy-token'])
      .then(() => undefined)
      .catch((error: unknown) => error);

    expect(outcome).toBeInstanceOf(ExitCalled);
    expect((outcome as ExitCalled).code).not.toBe(0);
    expect(stdout.join('')).toBe('');
    expect(stderr.join('')).toContain('A proxy token cannot mint another proxy token.');
  });
});
