/**
 * A device-code login nobody approved in time is a retryable AUTH_REQUIRED that names `rdc subscription login`.
 * Before 2026-09-26 it surfaced as VALIDATION_ERROR, not retryable, with the "Check command usage with --help"
 * guidance, although nothing about the command was wrong.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchMock, guardMock } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  guardMock: vi.fn(async () => undefined),
}));
vi.mock('../account-client.js', () => ({ accountServerFetch: fetchMock }));
vi.mock('../active-config-guard.js', () => ({ assertActiveConfigExists: guardMock }));

import { CliExitError } from '../../../utils/cli-exit-error.js';
import { outputService } from '../../core/output.js';
import {
  authorizeSubscriptionViaDeviceCode,
  withEmailPrefill,
} from '../subscription-device-auth.js';

const INIT = {
  deviceCode: 'dc',
  verificationUrl: 'https://example.com/a',
  interval: 1,
  expiresIn: 2,
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  fetchMock.mockReset();
});

async function settle(promise: Promise<unknown>): Promise<unknown> {
  const caught = promise.catch((e: unknown) => e);
  await vi.runAllTimersAsync();
  return caught;
}

describe('device-code login expiry', () => {
  it('the server answering `expired` is a retryable AUTH_REQUIRED naming the login command', async () => {
    fetchMock.mockResolvedValueOnce(INIT).mockResolvedValue({ status: 'expired' });

    const error = await settle(
      authorizeSubscriptionViaDeviceCode('https://example.com', { interactive: true })
    );

    expect(error).toBeInstanceOf(CliExitError);
    expect(error).toMatchObject({
      code: 'AUTH_REQUIRED',
      retryable: true,
      guidance: expect.stringContaining('rdc subscription login'),
    });
  });

  it('running out of polls while still pending is the same error', async () => {
    fetchMock.mockResolvedValueOnce(INIT).mockResolvedValue({ status: 'pending' });

    const error = await settle(
      authorizeSubscriptionViaDeviceCode('https://example.com', { interactive: true })
    );

    expect(error).toMatchObject({ code: 'AUTH_REQUIRED', retryable: true });
  });
});

describe('a named config that does not exist', () => {
  it('refuses before any request is made', async () => {
    guardMock.mockRejectedValueOnce(new Error('config "typo" does not exist'));
    await expect(
      authorizeSubscriptionViaDeviceCode('https://example.com', { interactive: true })
    ).rejects.toThrow('config "typo" does not exist');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('starts the device code when the config exists (control)', async () => {
    fetchMock.mockResolvedValueOnce(INIT).mockResolvedValue({ status: 'expired' });
    await settle(authorizeSubscriptionViaDeviceCode('https://example.com', { interactive: true }));
    expect(guardMock).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalled();
  });
});

describe('registration handoff URL', () => {
  it('prints the verification URL with the URL-encoded email and the device code', async () => {
    const info = vi.spyOn(outputService, 'info').mockImplementation(() => undefined);
    fetchMock
      .mockResolvedValueOnce({
        ...INIT,
        verificationUrl: 'https://example.com/account/authorize?code=ABCD-1234',
      })
      .mockResolvedValue({ status: 'expired' });

    await settle(
      authorizeSubscriptionViaDeviceCode('https://example.com', {
        interactive: true,
        email: 'a+b@example.com',
      })
    );

    const printed = info.mock.calls.map((c) => String(c[0])).find((l) => l.includes('/authorize'));
    info.mockRestore();
    expect(printed).toBeDefined();
    const url = new URL((printed ?? '').trim());
    expect(url.searchParams.get('code')).toBe('ABCD-1234');
    expect(url.searchParams.get('email')).toBe('a+b@example.com');
    expect(printed).toContain('email=a%2Bb%40example.com');
  });

  it('leaves a verification URL that is not absolute as the server sent it', () => {
    expect(withEmailPrefill('/verify?code=X', 'a@example.com')).toBe('/verify?code=X');
  });

  it('leaves the URL unchanged without an email', () => {
    expect(withEmailPrefill('https://example.com/a?code=X', undefined)).toBe(
      'https://example.com/a?code=X'
    );
  });
});
