/**
 * The truncated findings list: one loop, instead of thirty.
 *
 * WHY A SHARED MODULE. Measured 2026-09-24 across `scripts/gates/check-*.ts`: 21 files carried 30 hand-rolled copies of one loop, "print the first N findings, then `... and K more`", with only N differing. The copies had already drifted in the way copies do:
 *
 *   - SIX of them printed the first N and said NOTHING about the rest. `check-landmarks.ts` listed 15 pages with no `<main>` and dropped the sixteenth onward without a word, beside a sibling list in the same block that did say "... and K more". A list that truncates silently reads as the whole list, which is the vacuity this repo gates on.
 *   - `check-docs-untranslated-text.ts` capped its Layer 3 report at 30 ISSUES but computed its "... and K more file(s)" line against 30 FILES, so a report of 20 files with 3 issues each showed 10 files and hid the other 10 with no line saying so.
 *
 * Here the "more" line is not optional: a truncated list always says how much it hid.
 *
 * WHAT THIS DELIBERATELY DOES NOT OWN, for the reason `controls.ts` gives: the header and the remedy are the gate's own words and each gate's whole value. The caller passes them as strings, verbatim, and this module only decides how many items to print and what the tail says. Every `write` call receives exactly one caller string, so adopting it is byte-lossless for a site whose header and remedy already went out one call at a time.
 *
 * Its control is `.ci/rediacc_ci/tests/gates/test_gate_findings_report.py`: truncation exactly at N in both directions, the exit code of `refuseFindings`, and the refusal of a negative limit.
 */

export interface ListOptions<T> {
  /** Print at most this many items. `Infinity` prints every one (an `--all` flag). */
  limit: number;
  /** Prefixed to every item line AND to the "more" line. Default: four spaces. */
  indent?: string;
  /** One item as text. May return several lines for an item that spans more than one (a key with its old and new value); each is indented. Default: `String(item)`. */
  format?: (item: T) => string | readonly string[];
  /** The tail, given how many items were NOT printed. Default: `... and ${hidden} more`. */
  more?: (hidden: number) => string;
}

export interface WriteOptions {
  /** Where lines go. Default `console.error`, so a red survives a caller piping stdout. */
  write?: (line: string) => void;
}

export interface ReportOptions<T> extends ListOptions<T>, WriteOptions {
  /** The gate's own count sentence(s), written before the list, one `write` per string. */
  header: string | readonly string[];
  items: readonly T[];
  /** The gate's own fix instructions, written after the list, one `write` per string. */
  remedy?: string | readonly string[];
}

const DEFAULT_INDENT = '    ';
const defaultMore = (hidden: number): string => `... and ${hidden} more`;
const stderr = (l: string): void => console.error(l);

/**
 * The lines of a truncated list, as data. Pure, so a gate that collects its report into an array (rather than printing as it goes) uses the same rule as one that prints.
 *
 * A NEGATIVE OR NON-INTEGER LIMIT IS REFUSED rather than clamped: `slice(0, -3)` silently drops the LAST three items, and a limit computed from a bad subtraction is exactly the kind of number that goes negative without anyone noticing.
 */
export function truncatedLines<T>(items: readonly T[], opts: ListOptions<T>): string[] {
  const { limit } = opts;
  if (!(limit === Infinity || (Number.isInteger(limit) && limit >= 0))) {
    throw new Error(`truncatedLines: limit must be a non-negative integer, got ${limit}`);
  }
  const indent = opts.indent ?? DEFAULT_INDENT;
  const format = opts.format ?? ((x: T) => String(x));
  const more = opts.more ?? defaultMore;
  const out: string[] = [];
  const shown = Math.min(limit, items.length);
  for (let i = 0; i < shown; i++) {
    const f = format(items[i]);
    for (const line of typeof f === 'string' ? [f] : f) out.push(`${indent}${line}`);
  }
  const hidden = items.length - shown;
  if (hidden > 0) out.push(`${indent}${more(hidden)}`);
  return out;
}

/** `truncatedLines`, written one line per call. */
export function printTruncated<T>(items: readonly T[], opts: ListOptions<T> & WriteOptions): void {
  const write = opts.write ?? stderr;
  for (const line of truncatedLines(items, opts)) write(line);
}

/**
 * Header, truncated list, remedy; hands back the exit CODE, the way `refused` in `controls.ts` does, for a gate whose work happens in a `main(): number`.
 *
 * AN EMPTY `items` IS STILL A FAILURE, and says so. This is only reached on a path that has already decided the gate fails; a caller that got here with nothing to list has a broken predicate, and returning 0 would turn that into a green.
 */
export function reportFindings<T>(opts: ReportOptions<T>): 1 {
  const write = opts.write ?? stderr;
  for (const h of typeof opts.header === 'string' ? [opts.header] : opts.header) write(h);
  if (opts.items.length === 0) {
    write(`${opts.indent ?? DEFAULT_INDENT}(reportFindings was handed no findings to list)`);
  }
  printTruncated(opts.items, { ...opts, write });
  if (opts.remedy !== undefined) {
    for (const r of typeof opts.remedy === 'string' ? [opts.remedy] : opts.remedy) write(r);
  }
  return 1;
}

/** `reportFindings`, then exit 1. For a gate whose entry point is bare rather than `process.exit(main())`. */
export function refuseFindings<T>(opts: ReportOptions<T>): never {
  process.exit(reportFindings(opts));
}
