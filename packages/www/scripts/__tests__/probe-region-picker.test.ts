import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';
import en from '../../src/i18n/translations/en.json' with { type: 'json' };
import {
  isEntryPoint,
  LOOKUP_LABEL,
  parseArgs,
  REGION_STORAGE_KEY,
  STORAGE_SPY_SOURCE,
  USAGE_LINE,
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

const SCRIPT = fileURLToPath(new URL('../probe-region-picker.ts', import.meta.url));

describe('probe-region-picker entry point', () => {
  it('is the entry point under its own path and through a symlink, and not for another script', () => {
    const dir = mkdtempSync(join(tmpdir(), 'probe-entry-'));
    try {
      const link = join(dir, 'link.ts');
      symlinkSync(SCRIPT, link);
      expect(isEntryPoint(SCRIPT, pathToFileURL(SCRIPT).href)).toBe(true);
      expect(isEntryPoint(link, pathToFileURL(SCRIPT).href)).toBe(true);
      // Control: a different script, a missing path and no argv[1] are not it.
      expect(isEntryPoint(fileURLToPath(import.meta.url), pathToFileURL(SCRIPT).href)).toBe(false);
      expect(isEntryPoint(join(dir, 'absent.ts'), pathToFileURL(SCRIPT).href)).toBe(false);
      expect(isEntryPoint(undefined, pathToFileURL(SCRIPT).href)).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('a symlinked run refuses an unknown argument with exit 2 and the usage line, not a silent exit 0', () => {
    const dir = mkdtempSync(join(tmpdir(), 'probe-entry-'));
    try {
      const link = join(dir, 'link.ts');
      symlinkSync(SCRIPT, link);
      const run = spawnSync('npx', ['tsx', link, '--bogus'], {
        cwd: fileURLToPath(new URL('..', import.meta.url)),
        encoding: 'utf8',
      });
      expect(run.status).toBe(2);
      expect(run.stderr).toContain('unknown argument --bogus');
      expect(run.stderr).toContain(USAGE_LINE);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 60_000);
});
