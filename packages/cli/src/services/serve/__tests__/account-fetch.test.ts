import { describe, expect, it, vi } from 'vitest';
import {
  ACCOUNT_REQUEST_TIMEOUT_MS,
  deadlineFetch,
  describeFetchError,
  withAccountDeadline,
} from '../account-fetch.js';

describe('account fetch deadline', () => {
  it('adds an abort signal to every call', async () => {
    let seen: RequestInit | undefined;
    const wrapped = deadlineFetch((_input, init) => {
      seen = init;
      return Promise.resolve(new Response('{}'));
    });
    await wrapped('https://eu.example/account/api/v1/proxy/introspect', { method: 'POST' });
    expect(seen?.signal).toBeInstanceOf(AbortSignal);
    expect(seen?.method).toBe('POST');
  });

  it('keeps a signal the caller set', () => {
    const controller = new AbortController();
    expect(withAccountDeadline({ signal: controller.signal }).signal).toBe(controller.signal);
  });

  it('bounds the wait at a finite deadline', () => {
    expect(ACCOUNT_REQUEST_TIMEOUT_MS).toBeGreaterThan(0);
    expect(Number.isFinite(ACCOUNT_REQUEST_TIMEOUT_MS)).toBe(true);
  });

  it('hands the deadline to AbortSignal.timeout and a stalled call aborts when it fires', async () => {
    const spy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(AbortSignal.abort());
    const wrapped = deadlineFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
          if (init?.signal?.aborted) reject(new Error('aborted'));
        })
    );
    await expect(wrapped('https://eu.example/x')).rejects.toThrow('aborted');
    expect(spy).toHaveBeenCalledWith(ACCOUNT_REQUEST_TIMEOUT_MS);
    spy.mockRestore();
  });
});

describe('describeFetchError', () => {
  it('appends the undici cause code to "fetch failed"', () => {
    const error = new TypeError('fetch failed', { cause: { code: 'ECONNREFUSED' } });
    expect(describeFetchError(error)).toBe('fetch failed (ECONNREFUSED)');
  });

  it('falls back to the cause message, and leaves a plain error alone', () => {
    expect(
      describeFetchError(new Error('fetch failed', { cause: new Error('getaddrinfo ENOTFOUND x') }))
    ).toBe('fetch failed (getaddrinfo ENOTFOUND x)');
    expect(describeFetchError(new Error('boom'))).toBe('boom');
    expect(describeFetchError('raw')).toBe('raw');
  });
});
