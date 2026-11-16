import { describe, expect, it } from 'vitest';
import en from '../../src/i18n/translations/en.json' with { type: 'json' };
import {
  LOOKUP_LABEL,
  parseArgs,
  REGION_STORAGE_KEY,
  STORAGE_SPY_SOURCE,
  UsageError,
} from '../probe-region-picker.js';

describe('probe-region-picker arguments', () => {
  it('takes a positional host as the https origin to probe', () => {
    expect(parseArgs(['pr-605.rediacc.workers.dev'], {}).url).toBe(
      'https://pr-605.rediacc.workers.dev'
    );
  });

  it('keeps a positional origin that already names a scheme, without a trailing slash', () => {
    expect(parseArgs(['http://localhost:4321/'], {}).url).toBe('http://localhost:4321');
  });

  it('control: --url still selects the origin, and no argument keeps the default', () => {
    expect(parseArgs(['--url', 'https://x.example'], {}).url).toBe('https://x.example');
    expect(parseArgs([], {}).url).toBe('http://localhost:4321');
    expect(parseArgs([], { PROBE_URL: 'http://e.example' }).url).toBe('http://e.example');
  });

  it('control: the known flags still parse', () => {
    const opts = parseArgs(
      ['--mock', '--lookup-domain', 'd.example', '--lookup-host', 'h.example'],
      {}
    );
    expect(opts).toMatchObject({ mock: true, lookupDomain: 'd.example', lookupHost: 'h.example' });
  });

  it('refuses an unknown flag, a second positional, a doubled origin and a flag without a value', () => {
    expect(() => parseArgs(['--mok'], {})).toThrow(UsageError);
    expect(() => parseArgs(['a.example', 'b.example'], {})).toThrow(UsageError);
    expect(() => parseArgs(['--url', 'https://a.example', 'b.example'], {})).toThrow(UsageError);
    expect(() => parseArgs(['--url'], {})).toThrow(UsageError);
    expect(() => parseArgs(['--url', '--mock'], {})).toThrow(UsageError);
  });
});

describe('probe-region-picker selectors', () => {
  it('looks the lookup field up by the label the popup renders', () => {
    expect(LOOKUP_LABEL).toBe(en.regionPicker.lookup.label);
  });
});

describe('probe-region-picker storage spy', () => {
  it('reports a write the popup makes, then performs it', () => {
    const written: [string, string][] = [];
    const reported: [string, string][] = [];
    class FakeStorage {
      setItem(key: string, value: string): void {
        written.push([key, value]);
      }
    }
    const fakeWindow = { probeReportStored: (k: string, v: string) => reported.push([k, v]) };
    new Function('Storage', 'window', STORAGE_SPY_SOURCE)(FakeStorage, fakeWindow);
    new FakeStorage().setItem(REGION_STORAGE_KEY, '{"region":"eu"}');
    expect(reported).toEqual([[REGION_STORAGE_KEY, '{"region":"eu"}']]);
    expect(written).toEqual(reported);
  });
});
