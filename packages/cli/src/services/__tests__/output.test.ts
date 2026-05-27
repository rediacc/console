import { afterEach, describe, expect, it, vi } from 'vitest';
import { outputService } from '../output.js';

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
