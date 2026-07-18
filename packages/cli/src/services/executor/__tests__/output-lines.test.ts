/**
 * Line cleanup for renet's relayed output.
 *
 * The anchored-prefix cases are regressions: a looser `[^\]]+` pattern ate a
 * whole single-line JSON array payload, whose only `]` is its closing bracket.
 */

import { describe, expect, it } from 'vitest';
import { cleanRelayLine, isLogrusLine, stripRelayPrefix } from '../output-lines.js';

describe('stripRelayPrefix', () => {
  it('removes a bridge function prefix', () => {
    expect(stripRelayPrefix('[container_exec] hello')).toBe('hello');
  });

  it('leaves an unprefixed line alone', () => {
    expect(stripRelayPrefix('hello')).toBe('hello');
  });

  it('does NOT treat a JSON array as a prefix', () => {
    expect(stripRelayPrefix('[{"a":1},{"b":2}]')).toBe('[{"a":1},{"b":2}]');
  });

  it('does NOT strip a bracketed non-identifier, such as a timestamp', () => {
    expect(stripRelayPrefix('[2026-07-18] entry')).toBe('[2026-07-18] entry');
  });
});

describe('isLogrusLine', () => {
  it('detects a renet structured-log line', () => {
    expect(isLogrusLine('time="2026-07-18T19:09:33Z" level=info msg="Starting"')).toBe(true);
  });

  it('detects a level= line without the time prefix', () => {
    expect(isLogrusLine('[container_exec] level=warning msg="careful"')).toBe(true);
  });

  it('does not flag ordinary output that merely mentions a level', () => {
    expect(isLogrusLine('log level is high')).toBe(false);
  });
});

describe('cleanRelayLine', () => {
  it('returns the inner bytes for relayed program output', () => {
    expect(cleanRelayLine('[container_logs] app started')).toBe('app started');
  });

  it('drops logrus noise', () => {
    expect(cleanRelayLine('time="2026-07-18T19:09:33Z" level=info msg="x"')).toBeUndefined();
  });

  it('KEEPS a JSON log line, which the failure-path cleaner deliberately drops', () => {
    // Container logs are frequently structured JSON. Dropping them here would
    // re-create the bug this module exists to fix.
    expect(cleanRelayLine('[container_logs] {"level_of_detail":"high"}')).toBe(
      '{"level_of_detail":"high"}'
    );
  });

  it('preserves an empty line rather than swallowing it', () => {
    expect(cleanRelayLine('')).toBe('');
  });
});
