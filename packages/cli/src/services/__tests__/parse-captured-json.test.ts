import { describe, expect, it } from 'vitest';
import { parseCapturedJson } from '../executor/local-executor.js';

/**
 * parseCapturedJson (finding #10) parses a JSON payload out of a bridge
 * function's CAPTURED stdout. A bridge fn that shells out to a sub-`renet`
 * command has that sub-process stdout RELAYED with a `[function] ` line prefix,
 * so the captured stdout is NOT raw JSON. These cases use the REAL relay shape
 * (the reason #10 shipped: the fork/install unit tests stubbed CLEAN JSON, so
 * they never exercised the true capture path).
 */
describe('parseCapturedJson (bridge relay capture)', () => {
  it('parses a relay-prefixed JSON array (datastore_list)', () => {
    const stdout =
      '[datastore_list] [{"name":"default","backend":"local","implicit":true},' +
      '{"name":"ds-control-prod","backend":"ceph","cluster":"prod"}]';
    const records = parseCapturedJson<{ name: string; backend: string }[]>(stdout);
    expect(records.map((r) => r.name)).toEqual(['default', 'ds-control-prod']);
    expect(records[1].backend).toBe('ceph');
  });

  it('parses a relay-prefixed JSON object (ceph_client_config_export)', () => {
    const stdout = '[ceph_client_config_export] {"conf":"Y29uZg==","keyring":"a2V5"}';
    const payload = parseCapturedJson<{ conf: string; keyring: string }>(stdout);
    expect(payload).toEqual({ conf: 'Y29uZg==', keyring: 'a2V5' });
  });

  it('parses a RAW single-line JSON array with no relay prefix', () => {
    // The regression that broke the baseline tests: the old `[^\]]+` strip ate
    // the whole array (its only `]` is the closing bracket). The identifier-only
    // prefix strip must leave a bare array untouched.
    const stdout = '[{"name":"a"},{"name":"b"}]';
    const records = parseCapturedJson<{ name: string }[]>(stdout);
    expect(records.map((r) => r.name)).toEqual(['a', 'b']);
  });

  it('drops interleaved logrus lines whose bracketed message would fool the scan', () => {
    // datastore_fork emits a `[detached]` logrus line BEFORE the record; its
    // bracket must not be mistaken for the start of a JSON array (finding #10 v2).
    const stdout = [
      'time="2026-07-11T10:00:00Z" level=info msg="Adopted fork [detached]"',
      '[datastore_fork] {"name":"ds-control-prod:f5","backend":"ceph","fork":{"parent":"ds-control-prod","tag":"f5"}}',
    ].join('\n');
    const rec = parseCapturedJson<{ name: string; backend: string }>(stdout);
    expect(rec.name).toBe('ds-control-prod:f5');
    expect(rec.backend).toBe('ceph');
  });

  it('parses multi-line pretty-printed JSON after the relay prefix', () => {
    const stdout = ['[datastore_list] [', '  {"name":"a"},', '  {"name":"b"}', ']'].join('\n');
    const records = parseCapturedJson<{ name: string }[]>(stdout);
    expect(records.map((r) => r.name)).toEqual(['a', 'b']);
  });

  it('throws a descriptive error when there is no JSON payload', () => {
    expect(() => parseCapturedJson('[some_fn] just a log line, no json')).toThrow(
      /no JSON payload/
    );
  });
});
