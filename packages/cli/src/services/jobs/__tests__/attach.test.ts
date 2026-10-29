/**
 * The attach window per entry point, the request-id minter and the origin cap
 * (agent/plans/PLAN-detached-jobs.md sections 15, 17 and 19).
 */
import { describe, expect, it } from 'vitest';
import {
  attachFlagValue,
  attachWindowMs,
  clientKindFromEnv,
  isValidRequestId,
  JOB_ATTACH_WINDOW_ENV,
  JOB_ATTACH_WINDOW_MS,
  JOB_CLIENT_ENV,
  ORIGIN_MAX_BYTES,
  originJson,
  RequestIdMinter,
} from '../attach.js';

describe('attachWindowMs', () => {
  const direct = { background: false, served: false, client: 'rdc' as const };

  it('is unlimited on direct SSH, 0 under -b, 20 s for the proxy and MCP', () => {
    expect(JOB_ATTACH_WINDOW_MS).toBe(20_000);
    expect(attachWindowMs(direct, {})).toBeUndefined();
    expect(attachWindowMs({ ...direct, background: true }, {})).toBe(0);
    expect(attachWindowMs({ ...direct, served: true }, {})).toBe(20_000);
    expect(attachWindowMs({ ...direct, client: 'mcp' }, {})).toBe(20_000);
  });

  it('takes the test override of the window', () => {
    expect(attachWindowMs({ ...direct, served: true }, { [JOB_ATTACH_WINDOW_ENV]: '50' })).toBe(50);
    expect(attachWindowMs({ ...direct, served: true }, { [JOB_ATTACH_WINDOW_ENV]: 'x' })).toBe(
      20_000
    );
  });

  it('renders the --attach flag value, unlimited as 0s', () => {
    expect(attachFlagValue(undefined)).toBe('0s');
    expect(attachFlagValue(20_000)).toBe('20000ms');
  });

  it('reads the client kind from the environment, defaulting to rdc', () => {
    expect(clientKindFromEnv({ [JOB_CLIENT_ENV]: 'mcp' })).toBe('mcp');
    expect(clientKindFromEnv({ [JOB_CLIENT_ENV]: 'evil' })).toBe('rdc');
    expect(clientKindFromEnv({})).toBe('rdc');
  });
});

describe('RequestIdMinter', () => {
  it('mints <invocation>:<machine>:<seq>, counted per machine', () => {
    const minter = new RequestIdMinter('0b7a7c1e-4d2f-4c1b-9a3e-2f1d0c9b8a7e');
    expect(minter.next('prod-1')).toBe('0b7a7c1e-4d2f-4c1b-9a3e-2f1d0c9b8a7e:prod-1:1');
    expect(minter.next('prod-1')).toBe('0b7a7c1e-4d2f-4c1b-9a3e-2f1d0c9b8a7e:prod-1:2');
    expect(minter.next('prod-2')).toBe('0b7a7c1e-4d2f-4c1b-9a3e-2f1d0c9b8a7e:prod-2:1');
  });

  it('keeps every id inside renet request-id grammar, whatever the machine name', () => {
    const minter = new RequestIdMinter();
    const id = minter.next('my machine/../x');
    expect(isValidRequestId(id)).toBe(true);
  });

  it('refuses an invocation id renet would reject', () => {
    expect(() => new RequestIdMinter('../etc')).toThrow();
  });
});

describe('originJson', () => {
  it('carries the client, version and config', () => {
    expect(
      JSON.parse(originJson({ client: 'rdc', version: '1.0', config: { name: 'prod' } }))
    ).toEqual({
      client: 'rdc',
      version: '1.0',
      config: { name: 'prod' },
    });
  });

  it('drops fields to stay within the 1 KiB cap rather than fail the start', () => {
    const json = originJson({ client: 'proxy', version: '1.0', actor: 'a'.repeat(2000) });
    expect(Buffer.byteLength(json)).toBeLessThanOrEqual(ORIGIN_MAX_BYTES);
    expect(JSON.parse(json)).toEqual({ client: 'proxy', version: '1.0' });
  });
});
