import { afterEach, describe, expect, it, vi } from 'vitest';
import { outputService, wrapProse } from '../core/output.js';

/**
 * Regression guard for rediacc/console#490 bug #2 ("--output json polluted by
 * banner on stdout"). The contract that keeps `--output json` pipeable is:
 *
 *   - human/progress messages (info/success/warn/error) → STDERR (console.error)
 *   - the actual data payload (print) → STDOUT (console.log)
 *
 * So `rdc … --output json | jq` and `> out.json` stay clean even while progress
 * is shown. (The `./rdc.sh` dev-wrapper banner is separately routed to stderr via
 * `>&2` in .ci/lib/local-common.sh → common.sh; this test locks the CLI side.)
 */
describe('outputService stream routing (#490 bug 2)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    outputService.setQuiet(false);
  });

  it('routes info/success/warn/error to stderr, never stdout', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});

    outputService.info('preparing');
    outputService.success('done');
    outputService.warn('careful');
    outputService.error('boom');

    expect(err).toHaveBeenCalledTimes(4);
    expect(log).not.toHaveBeenCalled();
  });

  it('routes the data payload (print) to stdout only', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});

    outputService.print({ value: 42 }, 'json');

    expect(log).toHaveBeenCalledTimes(1);
    expect(err).not.toHaveBeenCalled();
    // What lands on stdout must be a single parseable JSON document (the
    // standard envelope), carrying the payload under `data`.
    const printed = (log.mock.calls[0]?.[0] ?? '') as string;
    expect(() => JSON.parse(printed)).not.toThrow();
    expect(JSON.parse(printed).data).toEqual({ value: 42 });
  });

  it('progress messages alongside json output leave stdout pure', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});

    // Simulate a command: progress, then the JSON document.
    outputService.info('Starting CLI (dev mode)');
    outputService.print({ data: 'x' }, 'json');

    // Exactly one stdout write, and it is valid JSON.
    expect(log).toHaveBeenCalledTimes(1);
    expect(() => JSON.parse(log.mock.calls[0]?.[0] as string)).not.toThrow();
  });
});

/**
 * Regression guard: a table that ALREADY FITS must still render.
 *
 * `fitColumnWidths` returns undefined when no shrinking is needed, and that value
 * was passed straight through as `colWidths: undefined`. cli-table3 reads
 * `options.colWidths[0]` unconditionally, so the explicit undefined threw
 * "Cannot read properties of undefined (reading '0')" and every narrow table died
 * - which is most of them. It escaped review because the change was verified
 * against the 147-column `config show` case, the one path where the value is an
 * array. `rdc repo list` (2 short columns) crashed on a live recording.
 */
describe('outputService table sizing', () => {
  const narrow = [{ name: 'my-app', machine: 'machine-11' }];
  const wide = [
    {
      guid: 'aaae8b44-0000-1111-2222-333344445555',
      note: 'x'.repeat(200),
      machine: 'machine-11',
    },
  ];
  const STRIP_ANSI = new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*m`, 'g');

  it('renders a table that needs no shrinking', () => {
    expect(() => outputService.formatTable(narrow)).not.toThrow();
    expect(outputService.formatTable(narrow)).toContain('my-app');
  });

  it('still constrains a table that overflows the budget', () => {
    const rendered = outputService.formatTable(wide);
    const widest = Math.max(
      ...rendered.split('\n').map((l) => l.replaceAll(STRIP_ANSI, '').length)
    );
    expect(widest).toBeLessThanOrEqual(Math.max(process.stdout.columns || 80, 80));
  });

  it('renders an empty result set without throwing', () => {
    expect(() => outputService.formatTable([])).not.toThrow();
  });
});

/**
 * `wrapProse` shipped in the same change as the colWidths regression and had no
 * tests at all, which is precisely how that one reached a live recording. These
 * lock the four behaviours its doc comment promises.
 */
describe('wrapProse', () => {
  it('breaks on spaces at the width', () => {
    expect(wrapProse('aaa bbb ccc ddd', 7)).toEqual(['aaa bbb', 'ccc ddd']);
  });

  it('leaves an over-long token INTACT and emits no blank filler line', () => {
    const url = `https://example.com/${'x'.repeat(80)}`;
    // The long token must come FIRST. The `line === ''` guard only fires against an
    // EMPTY accumulator, so a short word ahead of it makes both branches behave
    // identically and the test proves nothing (verified by mutation: it stayed
    // green with the guard removed).
    const out = wrapProse(`${url} trailing words here`, 20);
    expect(out).toContain(url);
    expect(out.filter((l) => l.trim() === '')).toEqual([]);
  });

  it('preserves existing newlines as paragraph boundaries', () => {
    expect(wrapProse('short\nalso short', 40)).toEqual(['short', 'also short']);
  });

  it('keeps the leading indent on continuation lines', () => {
    const out = wrapProse('    alpha beta gamma delta', 14);
    expect(out.length).toBeGreaterThan(1);
    for (const line of out) expect(line.startsWith('    ')).toBe(true);
  });

  it('returns the text untouched for a non-positive width', () => {
    expect(wrapProse('a b c', 0)).toEqual(['a b c']);
  });
});
