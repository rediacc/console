/**
 * ensureRebound without a terminal: the code comes from REDIACC_IP_REBIND_CODE,
 * is POSTed once, and a malformed or unset value never reaches the route. The
 * terminal path stays the prompt loop.
 */

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
vi.mock('../../core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../core/request-context.js')>()),
  writeStderr: mockWriteStderr,
}));

import { ensureRebound, IP_REBIND_CODE_ENV, resetTokenIpRebindState } from '../token-ip-rebind.js';

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
});
