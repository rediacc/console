import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../account-client.js', () => ({
  accountServerFetch: vi.fn(),
}));

import { accountServerFetch } from '../account-client.js';
import {
  credentialsToBasicAuthToken,
  fetchOtlpCredentials,
  resetOtlpCredentialsCache,
} from '../otlp-credentials.js';

const mockedFetch = vi.mocked(accountServerFetch);

describe('fetchOtlpCredentials', () => {
  beforeEach(() => {
    resetOtlpCredentialsCache();
    vi.resetAllMocks();
  });

  afterEach(() => {
    resetOtlpCredentialsCache();
  });

  it('calls GET /account/api/v1/telemetry/config with noAuth=true', async () => {
    mockedFetch.mockResolvedValue({
      otlp: { endpoint: 'otlp.rediacc.io', user: 'u', pass: 'p' },
    });

    await fetchOtlpCredentials();

    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(mockedFetch).toHaveBeenCalledWith('/account/api/v1/telemetry/config', {
      noAuth: true,
    });
  });

  it('returns credentials when the server provides them', async () => {
    mockedFetch.mockResolvedValue({
      otlp: { endpoint: 'otlp.rediacc.io', user: 'otlp-eu-abc', pass: 'pass-xyz' },
    });

    const result = await fetchOtlpCredentials();

    expect(result).toEqual({
      endpoint: 'otlp.rediacc.io',
      user: 'otlp-eu-abc',
      pass: 'pass-xyz',
    });
  });

  it('returns null when the server explicitly returns otlp:null', async () => {
    mockedFetch.mockResolvedValue({ otlp: null });

    const result = await fetchOtlpCredentials();

    expect(result).toBeNull();
  });

  it('never throws: treats fetch errors as "disabled"', async () => {
    mockedFetch.mockRejectedValue(new Error('network down'));

    const result = await fetchOtlpCredentials();

    expect(result).toBeNull();
  });

  it('caches the result across calls within one process', async () => {
    mockedFetch.mockResolvedValue({
      otlp: { endpoint: 'otlp.rediacc.io', user: 'u', pass: 'p' },
    });

    await fetchOtlpCredentials();
    await fetchOtlpCredentials();
    await fetchOtlpCredentials();

    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it("caches null results (doesn't retry failures)", async () => {
    mockedFetch.mockRejectedValue(new Error('network down'));

    await fetchOtlpCredentials();
    await fetchOtlpCredentials();
    await fetchOtlpCredentials();

    // Fetch should be attempted once, the null is cached
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it('resets the cache via resetOtlpCredentialsCache', async () => {
    mockedFetch.mockResolvedValueOnce({ otlp: null });
    await fetchOtlpCredentials();
    expect(mockedFetch).toHaveBeenCalledTimes(1);

    resetOtlpCredentialsCache();
    mockedFetch.mockResolvedValueOnce({
      otlp: { endpoint: 'otlp.rediacc.io', user: 'u', pass: 'p' },
    });

    const result = await fetchOtlpCredentials();
    expect(result?.user).toBe('u');
    expect(mockedFetch).toHaveBeenCalledTimes(2);
  });

  it('returns null when the response is missing the otlp field', async () => {
    mockedFetch.mockResolvedValue({} as never);

    const result = await fetchOtlpCredentials();

    expect(result).toBeNull();
  });
});

describe('credentialsToBasicAuthToken', () => {
  it('base64-encodes user:pass', () => {
    const encoded = credentialsToBasicAuthToken({
      endpoint: 'otlp.rediacc.io',
      user: 'alice',
      pass: 'secret',
    });
    expect(encoded).toBe(Buffer.from('alice:secret').toString('base64'));
  });

  it('handles passwords with special characters', () => {
    const encoded = credentialsToBasicAuthToken({
      endpoint: 'otlp.rediacc.io',
      user: 'u',
      pass: 'p@ss:word!',
    });
    expect(Buffer.from(encoded, 'base64').toString()).toBe('u:p@ss:word!');
  });
});
