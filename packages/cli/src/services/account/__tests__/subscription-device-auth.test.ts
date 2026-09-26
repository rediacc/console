/**
 * A device-code login nobody approved in time is a retryable AUTH_REQUIRED that names `rdc subscription login`.
 * Before 2026-09-26 it surfaced as VALIDATION_ERROR, not retryable, with the "Check command usage with --help"
 * guidance, although nothing about the command was wrong.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
vi.mock('../account-client.js', () => ({ accountServerFetch: fetchMock }));

import { CliExitError } from '../../../utils/cli-exit-error.js';
import { authorizeSubscriptionViaDeviceCode } from '../subscription-device-auth.js';

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
