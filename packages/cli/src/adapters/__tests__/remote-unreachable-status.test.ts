/**
 * A 5xx is grouped with "unreachable" so a read can fall back to the offline cache, but the message names the
 * status when the server answered. On 2026-09-26 a push the server failed with HTTP 500 was reported as
 * "which is unreachable", which sent the diagnosis to the network instead of the server.
 */

import { describe, expect, it } from 'vitest';
import { ConfigServerError } from '../../services/config/config-server-client.js';
import { RemoteUnreachableError, RemoteWriteFailedClosedError } from '../remote-config-errors.js';

const SERVER = 'https://eu.example.com';

describe('RemoteUnreachableError names the status when the server answered', () => {
  it('a 5xx says the server answered with an error and names the status', () => {
    const error = new RemoteUnreachableError(SERVER, new ConfigServerError('boom', 500));
    expect(error.status).toBe(500);
    expect(error.message).toContain('500');
    expect(error.message).not.toMatch(/unreachable/i);
  });

  it('a network failure still says unreachable', () => {
    const error = new RemoteUnreachableError(SERVER, new TypeError('fetch failed'));
    expect(error.status).toBeUndefined();
    expect(error.message).toMatch(/unreachable/i);
  });

  it('a fail-closed write carries the status through', () => {
    const cause = new RemoteUnreachableError(SERVER, new ConfigServerError('boom', 502));
    const error = new RemoteWriteFailedClosedError('rediacc', SERVER, cause);
    expect(error.message).toContain('502');
    expect(error.message).toContain('NOT saved');
    expect(error.message).not.toMatch(/unreachable/i);
  });
});
