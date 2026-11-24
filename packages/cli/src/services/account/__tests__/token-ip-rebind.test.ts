/**
 * ensureRebound without a terminal: the code comes from REDIACC_IP_REBIND_CODE,
 * is POSTed once, and a malformed or unset value never reaches the route. The
 * terminal path stays the prompt loop.
 */

import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  API_TOKEN_IP_REBIND_ERROR_CODES,
  TOKEN_IP_MISMATCH,
} from '@rediacc/shared/subscription/types';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockAskInput = vi.hoisted(() =>
  vi.fn<(message: string, pattern: RegExp) => Promise<string>>()
);
const mockWriteStderr = vi.hoisted(() => vi.fn());

vi.mock('../../../utils/prompt.js', () => ({ askInput: mockAskInput }));
vi.mock('../../../utils/spinner.js', () => ({
  suspendSpinner: <T>(fn: () => Promise<T>): Promise<T> => fn(),
}));
vi.mock('../../config/config-name.js', () => ({ getEffectiveConfigName: () => 'eu-bench' }));
vi.mock('../../core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../core/request-context.js')>()),
  writeStderr: mockWriteStderr,
}));

import {
  ensureRebound,
  IP_REBIND_CODE_COMMAND_ENV,
  IP_REBIND_CODE_ENV,
  resetTokenIpRebindState,
} from '../token-ip-rebind.js';

const CODE = '123456';
let tokenSeq = 0;

function setTty(value: boolean): void {
  Object.defineProperty(process.stdin, 'isTTY', { value, configurable: true });
  Object.defineProperty(process.stderr, 'isTTY', { value, configurable: true });
}

function input(rebind: (code: string) => Promise<{ boundIp: string }>) {
  tokenSeq += 1;
  return {
    token: `rdc_token_${tokenSeq}`,
    hint: 'totp' as const,
    rebind: rebind as never,
  };
}

function stderrText(): string {
  return mockWriteStderr.mock.calls.map((call) => String(call[0])).join('');
}

describe('ensureRebound', () => {
  const stdinTty = process.stdin.isTTY;
  const stderrTty = process.stderr.isTTY;

  beforeEach(() => {
    resetTokenIpRebindState();
    mockAskInput.mockReset();
    mockWriteStderr.mockReset();
    delete process.env[IP_REBIND_CODE_ENV];
    setTty(false);
  });

  afterEach(() => {
    delete process.env[IP_REBIND_CODE_ENV];
    Object.defineProperty(process.stdin, 'isTTY', {
      value: stdinTty,
      configurable: true,
    });
    Object.defineProperty(process.stderr, 'isTTY', {
      value: stderrTty,
      configurable: true,
    });
  });

  it('POSTs the environment code once without a terminal and never echoes it', async () => {
    process.env[IP_REBIND_CODE_ENV] = CODE;
    const rebind = vi.fn(() => Promise.resolve({ boundIp: '203.0.113.7' }));

    await ensureRebound(input(rebind));

    expect(rebind).toHaveBeenCalledTimes(1);
    expect(rebind).toHaveBeenCalledWith(CODE);
    expect(mockAskInput).not.toHaveBeenCalled();
    expect(stderrText()).toContain('203.0.113.7');
    expect(stderrText()).not.toContain(CODE);
  });

  it('refuses a malformed environment code before any POST', async () => {
    process.env[IP_REBIND_CODE_ENV] = '12345a';
    const rebind = vi.fn(() => Promise.resolve({ boundIp: '203.0.113.7' }));

    const error = await ensureRebound(input(rebind)).catch((e: unknown) => e);

    expect(rebind).not.toHaveBeenCalled();
    expect(error).toMatchObject({ status: 403, code: TOKEN_IP_MISMATCH });
    expect((error as Error).message).toContain(IP_REBIND_CODE_ENV);
    expect((error as Error).message).not.toContain('12345a');
  });

  it('keeps the non-interactive refusal when the variable is unset (control)', async () => {
    const rebind = vi.fn(() => Promise.resolve({ boundIp: '203.0.113.7' }));

    const error = await ensureRebound(input(rebind)).catch((e: unknown) => e);

    expect(rebind).not.toHaveBeenCalled();
    expect(error).toMatchObject({ status: 403, code: TOKEN_IP_MISMATCH });
    expect((error as Error).message).toContain('interactive terminal');
    expect((error as Error).message).toContain(IP_REBIND_CODE_ENV);
  });

  it('fails a wrong environment code with the retryable message and no second POST', async () => {
    process.env[IP_REBIND_CODE_ENV] = CODE;
    const rebind = vi.fn(() =>
      Promise.reject(
        Object.assign(new Error('bad code'), {
          status: 403,
          code: API_TOKEN_IP_REBIND_ERROR_CODES.TOTP_INVALID,
          details: { attemptsRemaining: 4 },
        })
      )
    );

    const error = await ensureRebound(input(rebind)).catch((e: unknown) => e);

    expect(rebind).toHaveBeenCalledTimes(1);
    expect(error).toMatchObject({ status: 403, code: TOKEN_IP_MISMATCH });
    expect((error as Error).message).toContain('4 tries left');
    expect((error as Error).message).not.toContain(CODE);
  });

  it('fails a reused environment code with the replayed message and no second POST', async () => {
    process.env[IP_REBIND_CODE_ENV] = CODE;
    const rebind = vi.fn(() =>
      Promise.reject(
        Object.assign(new Error('replayed'), {
          status: 403,
          code: API_TOKEN_IP_REBIND_ERROR_CODES.TOTP_REPLAYED,
        })
      )
    );

    const error = await ensureRebound(input(rebind)).catch((e: unknown) => e);

    expect(rebind).toHaveBeenCalledTimes(1);
    expect((error as Error).message).toContain('already used');
  });

  it('asks on a terminal and ignores the environment code there', async () => {
    setTty(true);
    process.env[IP_REBIND_CODE_ENV] = '999999';
    mockAskInput.mockResolvedValueOnce(CODE);
    const rebind = vi.fn(() => Promise.resolve({ boundIp: '203.0.113.7' }));

    await ensureRebound(input(rebind));

    expect(mockAskInput).toHaveBeenCalledTimes(1);
    expect(rebind).toHaveBeenCalledTimes(1);
    expect(rebind).toHaveBeenCalledWith(CODE);
  });

  describe('the code program', () => {
    let dir: string;

    function program(body: string): string {
      const path = join(dir, 'code.sh');
      writeFileSync(path, `#!/bin/sh\n${body}\n`);
      chmodSync(path, 0o755);
      process.env[IP_REBIND_CODE_COMMAND_ENV] = path;
      return path;
    }

    beforeEach(() => {
      dir = mkdtempSync(join(tmpdir(), 'rdc-rebind-cmd-'));
    });

    afterEach(() => {
      delete process.env[IP_REBIND_CODE_COMMAND_ENV];
      rmSync(dir, { recursive: true, force: true });
    });

    it('POSTs the code the program prints for the active config, on a terminal too', async () => {
      setTty(true);
      program('[ "$1" = eu-bench ] && echo 246810');
      const rebind = vi.fn(() => Promise.resolve({ boundIp: '203.0.113.7' }));

      await ensureRebound(input(rebind));

      expect(rebind).toHaveBeenCalledTimes(1);
      expect(rebind).toHaveBeenCalledWith('246810');
      expect(mockAskInput).not.toHaveBeenCalled();
      expect(stderrText()).not.toContain('246810');
    });

    it('a failing program is a named refusal quoting its stderr, with no POST', async () => {
      const path = program('echo "BENCH_ROOT_TOTP_SEED is unset" >&2; exit 2');
      const rebind = vi.fn(() => Promise.resolve({ boundIp: '203.0.113.7' }));

      const error = await ensureRebound(input(rebind)).catch((e: unknown) => e);

      expect(rebind).not.toHaveBeenCalled();
      expect(error).toMatchObject({ status: 403, code: TOKEN_IP_MISMATCH });
      const message = (error as Error).message;
      expect(message).toContain(IP_REBIND_CODE_COMMAND_ENV);
      expect(message).toContain(path);
      expect(message).toContain('exit 2');
      expect(message).toContain('BENCH_ROOT_TOTP_SEED is unset');
    });

    it('a program printing something other than six digits is refused without echoing it', async () => {
      program('echo 12345x');
      const rebind = vi.fn(() => Promise.resolve({ boundIp: '203.0.113.7' }));

      const error = await ensureRebound(input(rebind)).catch((e: unknown) => e);

      expect(rebind).not.toHaveBeenCalled();
      expect((error as Error).message).toContain('something other than a 6-digit code');
      expect((error as Error).message).not.toContain('12345x');
    });

    it('a missing program is a named refusal, not a hang', async () => {
      process.env[IP_REBIND_CODE_COMMAND_ENV] = join(dir, 'absent');
      const rebind = vi.fn(() => Promise.resolve({ boundIp: '203.0.113.7' }));

      const error = await ensureRebound(input(rebind)).catch((e: unknown) => e);

      expect(rebind).not.toHaveBeenCalled();
      expect((error as Error).message).toContain('ENOENT');
    });

    it('an explicit REDIACC_IP_REBIND_CODE wins over the program (control)', async () => {
      program('echo 999999');
      process.env[IP_REBIND_CODE_ENV] = CODE;
      const rebind = vi.fn(() => Promise.resolve({ boundIp: '203.0.113.7' }));

      await ensureRebound(input(rebind));

      expect(rebind).toHaveBeenCalledWith(CODE);
    });
  });
});
