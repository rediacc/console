/**
 * The bench-only reachability drill seam (src/drill.ts, PLAN-org-executor-connect-timeout-relocate box E15): the probe of the drill's `from` goes to its `to` on bench and nowhere else.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { drillProbeTarget } from '../drill';

const VAR = '192.0.2.10:22=203.0.113.7:22';
const FROM = { host: '192.0.2.10', port: 22 };
const TO = { host: '203.0.113.7', port: 22 };

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('drillProbeTarget', () => {
  it('on bench, a report of the drill address is probed at the redirect target', () => {
    expect(drillProbeTarget({ ENVIRONMENT: 'bench', EGRESS_DRILL_PROBE: VAR }, FROM, 2)).toEqual(
      TO
    );
    expect(console.warn).toHaveBeenCalledWith(
      'proxy: org executor reachability drill redirect at p2'
    );
    expect(JSON.stringify(vi.mocked(console.warn).mock.calls)).not.toMatch(/192\.0|203\.0/);
  });

  it.each(['edge', 'production', undefined])(
    'with ENVIRONMENT %s the same var changes nothing',
    (environment) => {
      const env = { ENVIRONMENT: environment, EGRESS_DRILL_PROBE: VAR };
      expect(drillProbeTarget(env, FROM, 0)).toBe(FROM);
      expect(console.warn).not.toHaveBeenCalled();
    }
  );

  it('a report of another address is probed where it points', () => {
    const env = { ENVIRONMENT: 'bench', EGRESS_DRILL_PROBE: VAR };
    const other = { host: '198.51.100.4', port: 22 };
    expect(drillProbeTarget(env, other, 0)).toBe(other);
    const otherPort = { host: '192.0.2.10', port: 2222 };
    expect(drillProbeTarget(env, otherPort, 0)).toBe(otherPort);
    expect(drillProbeTarget(env, undefined, 0)).toBeUndefined();
  });

  it('accepts bracketed IPv6 on either side', () => {
    const env = {
      ENVIRONMENT: 'bench',
      EGRESS_DRILL_PROBE: '[2001:db8::1]:22=[2001:db8::2]:2222',
    };
    expect(drillProbeTarget(env, { host: '2001:db8::1', port: 22 }, 0)).toEqual({
      host: '2001:db8::2',
      port: 2222,
    });
  });

  it.each([
    '',
    '192.0.2.10:22',
    '192.0.2.10:22=',
    '=203.0.113.7:22',
    '192.0.2.10:22=203.0.113.7:22=198.51.100.4:22',
    '192.0.2.10=203.0.113.7:22',
    '192.0.2.10:22=203.0.113.7',
    '192.0.2.10:22 = 203.0.113.7:22',
    '192.0.2.10:ssh=203.0.113.7:22',
    '192.0.2.10:22=203.0.113.7:70000',
    '192.0.2.10:22=2001:db8::2:22',
    '192.0.2.10:22=10.0.0.1:22',
    '192.0.2.10:22=127.0.0.1:22',
    '192.0.2.10:22=[::1]:22',
    '192.0.2.10:22=203.0.113.7:25',
    '192.0.2.10:22=localhost:22',
  ])('a malformed or refused var %j leaves the report as it is', (raw) => {
    const env = { ENVIRONMENT: 'bench', EGRESS_DRILL_PROBE: raw };
    expect(drillProbeTarget(env, FROM, 0)).toBe(FROM);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('an unset var on bench leaves the report as it is', () => {
    expect(drillProbeTarget({ ENVIRONMENT: 'bench' }, FROM, 0)).toBe(FROM);
  });
});
