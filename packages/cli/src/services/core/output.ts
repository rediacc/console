/* eslint-disable no-console */

import { DEFAULTS } from '@rediacc/shared/config';
import { formatPropertyName, formatTimestampAsIs, formatValue } from '@rediacc/shared/formatters';
import { escapeCSVValue } from '@rediacc/shared/utils';
import chalk from 'chalk';
import type CliTable3 from 'cli-table3';
import { stringify as yamlStringify } from 'yaml';
import type { OutputFormat } from '../../types/index.js';
import { createOutputState, currentRequestContext, type OutputState } from './request-context.js';

// esbuild statically bundles this literal `require` and wraps cli-table3
// (→ string-width → chardet, ~16 ms of module init) in a lazy CJS
// initializer that only runs the first time a table is actually rendered.
// A top-level `import` would run it eagerly on every startup, including
// --version/--help/JSON-output runs that never draw a table.
declare const require: NodeJS.Require;
let TableCtor: typeof CliTable3 | undefined;
function loadTable(): typeof CliTable3 {
  TableCtor ??= require('cli-table3') as typeof CliTable3;
  return TableCtor;
}

interface TableColumn {
  key: string;
  header: string;
  width?: number;
  align?: 'left' | 'center' | 'right';
  format?: (value: unknown) => string;
}

/**
 * cli-table3's `colWidths` are FULL cell widths: they already include the one
 * space of padding on each side. Only the `│` separators are extra, and there
 * are (columns + 1) of them. Modelling the padding as extra chrome instead
 * under-sizes every column and ellipsises content that had room -- measured:
 * a 107-column budget produced an 87-column table of "Vers…"/"Adap…"/"1880…".
 */
const CELL_PADDING = 2;
/** Below this a column shows nothing useful, so stop shrinking and overflow honestly. */
const MIN_COL_WIDTH = 8;

/**
 * Columns available on the destination terminal.
 *
 * Not a TTY (a pipe, a CI log, an asciinema recording harness) has no width, so
 * fall back to the POSIX default of 80 rather than to "unlimited" -- unlimited
 * is what produced the 147-column table that no terminal could hold.
 */
export function terminalWidth(): number {
  const cols = process.stdout.columns;
  if (typeof cols === 'number' && cols > 0) return cols;
  const env = Number.parseInt(process.env.COLUMNS ?? '', 10);
  return Number.isFinite(env) && env > 0 ? env : 80;
}

/**
 * Per-column widths that make the table fit `budget`, or null to let cli-table3
 * size it naturally when it already fits.
 *
 * Shrinks the widest column repeatedly rather than scaling everything down, so
 * a table blown out by one long id (a 36-char GUID) keeps its short columns
 * intact instead of wrapping every one of them.
 */
function fitColumnWidths(
  cols: { key: string; header: string }[],
  items: Record<string, unknown>[],
  budget: number
): number[] | undefined {
  const natural = cols.map(
    (c) =>
      Math.max(
        c.header.length,
        ...items.map((it) => {
          const v = it[c.key];
          return v === null || v === undefined ? 0 : String(v).length;
        })
      ) + CELL_PADDING
  );
  const chrome = cols.length + 1; // the `│` separators, nothing else
  const total = () => natural.reduce((a, b) => a + b, 0) + chrome;
  if (total() <= budget) return undefined;

  // Shrink the current widest column by one until it fits or nothing can give.
  let guard = 10_000;
  while (total() > budget && guard-- > 0) {
    let widest = 0;
    for (let i = 1; i < natural.length; i++) if (natural[i] > natural[widest]) widest = i;
    if (natural[widest] <= MIN_COL_WIDTH) break;
    natural[widest] -= 1;
  }
  return natural;
}

/**
 * Break prose to `width`, on spaces only.
 *
 * A token longer than the width (a URL, a GUID, a path) is left INTACT on its own
 * line: breaking those makes them uncopyable, which is worse than one long line.
 * Existing newlines are preserved, so multi-line messages keep their shape.
 *
 * Wrapping happens before colouring. Doing it after would slice through a chalk
 * escape sequence and leave the colour open across the break.
 */
function wrapParagraph(paragraph: string, width: number): string[] {
  if (paragraph.length <= width) return [paragraph];
  // Keep any leading indent on continuation lines so lists stay aligned.
  const indent = /^\s*/.exec(paragraph)?.[0] ?? '';
  const out: string[] = [];
  let line = '';
  for (const word of paragraph.trimStart().split(/\s+/)) {
    const candidate = line ? `${line} ${word}` : `${indent}${word}`;
    // `line === ''` keeps an over-long token INTACT on its own line.
    if (candidate.length <= width || line === '') {
      line = candidate;
    } else {
      out.push(line);
      line = `${indent}${word}`;
    }
  }
  if (line) out.push(line);
  return out;
}

export function wrapProse(text: string, width: number): string[] {
  if (width <= 0) return [text];
  return text.split('\n').flatMap((paragraph) => wrapParagraph(paragraph, width));
}

class OutputService {
  private readonly ttyColor: boolean;
  /** Used when no request context is active: the CLI, one command per process. */
  private readonly processState: OutputState = createOutputState();

  constructor() {
    // NO_COLOR standard (https://no-color.org): any non-empty value disables color.
    const noColor = process.env.NO_COLOR !== undefined && process.env.NO_COLOR !== '';
    this.ttyColor = !noColor && process.stdout.isTTY !== false;
  }

  /**
   * The state of the command being run right now.
   *
   * Inside an executor dispatch that is the request's own state, so two tenants'
   * commands cannot overwrite each other's command name, warnings or timings on
   * the way into the JSON envelope. On a laptop it is the process's.
   */
  private get state(): OutputState {
    return currentRequestContext()?.output ?? this.processState;
  }

  /** Captured output is read by a machine, so it never carries ANSI colour. */
  private get colorEnabled(): boolean {
    return currentRequestContext() ? false : this.ttyColor;
  }

  /** Data output: the terminal, or this request's stdout buffer. */
  private writeOut(text: string): void {
    const context = currentRequestContext();
    if (context) context.stdout.push(text);
    else console.log(text);
  }

  /** Human output: the terminal's stderr, or this request's stderr buffer. */
  private writeErr(text: string): void {
    const context = currentRequestContext();
    if (context) context.stderr.push(text);
    else console.error(text);
  }

  /**
   * Human-facing prose, wrapped to the terminal.
   *
   * Not wrapped when a request context is active: that buffer feeds the JSON
   * envelope consumed by the console and MCP, where inserted newlines would be
   * data corruption rather than layout.
   */
  private writeProse(message: string, paint: (line: string) => string): void {
    const context = currentRequestContext();
    if (context) {
      context.stderr.push(message);
      return;
    }
    for (const line of wrapProse(message, terminalWidth())) console.error(paint(line));
  }

  setQuiet(quiet: boolean): void {
    this.state.quiet = quiet;
  }

  setFields(fields: string): void {
    this.state.fields = fields.split(',').map((f) => f.trim());
  }

  setCommandContext(name: string, startTime: number): void {
    const state = this.state;
    state.commandName = name;
    state.startTime = startTime;
    state.warnings = [];
  }

  getCommandName(): string | null {
    return this.state.commandName;
  }

  getWarnings(): string[] {
    return this.state.warnings;
  }

  getDurationMs(): number {
    const startTime = this.state.startTime;
    return startTime ? Date.now() - startTime : 0;
  }

  setOperationDuration(ms: number): void {
    this.state.operationDurationMs = ms;
  }

  /** Mark that a timeline was rendered — suppresses the postAction "Completed" line */
  setTimelineRendered(): void {
    this.state.timelineRendered = true;
  }

  private applyFieldFilter<T extends Record<string, unknown>>(data: T | T[]): T | T[] {
    const fields = this.state.fields;
    if (!fields) return data;
    const pick = (obj: T): T => {
      const result: Record<string, unknown> = {};
      for (const field of fields) {
        if (field in obj) result[field] = obj[field];
      }
      return result as T;
    };
    return Array.isArray(data) ? data.map(pick) : pick(data);
  }

  format<T extends Record<string, unknown>>(
    data: T | T[],
    format: OutputFormat = 'table',
    columns?: TableColumn[]
  ): string {
    const filtered = this.applyFieldFilter(data);
    switch (format) {
      case 'json':
        return this.formatJson(filtered);
      case 'yaml':
        return this.formatYaml(filtered);
      case 'csv':
        return this.formatCsv(filtered, columns);
      case 'table':
      default:
        return this.formatTable(filtered, columns);
    }
  }

  formatJson<T>(data: T): string {
    const state = this.state;
    const envelope = {
      success: true,
      command: state.commandName ?? DEFAULTS.TELEMETRY.UNKNOWN,
      data,
      errors: null,
      warnings: state.warnings,
      metrics: {
        duration_ms: this.getDurationMs(),
        ...(state.operationDurationMs != null && {
          operation_duration_ms: state.operationDurationMs,
        }),
      },
    };
    return JSON.stringify(envelope, null, 2);
  }

  formatYaml<T>(data: T): string {
    return yamlStringify(data);
  }

  formatTable<T extends Record<string, unknown>>(data: T | T[], columns?: TableColumn[]): string {
    const items = Array.isArray(data) ? data : [data];
    if (items.length === 0) {
      return this.dim('No data to display');
    }

    // Auto-detect columns if not provided
    const cols = columns ?? this.detectColumns(items);
    if (cols.length === 0) {
      return this.dim('No columns to display');
    }

    const Table = loadTable();
    // Without these two, a table wider than the terminal is emitted at its
    // natural width and the TERMINAL wraps it: the overflowing columns land
    // on the next physical line and interleave with the row below, which
    // shreds the box-drawing borders into unreadable noise. `rdc config show`
    // is 147 columns and did exactly that on any terminal narrower than that,
    // including every recorded tutorial (107 cols) and any 80-column SSH
    // session. wordWrap makes cli-table3 wrap INSIDE each cell instead.
    //
    // colWidths must be OMITTED, not passed as undefined, when the table already
    // fits. cli-table3 reads options.colWidths[0] unconditionally, so an explicit
    // undefined throws "Cannot read properties of undefined (reading '0')" and
    // takes down every table narrow enough to need no shrinking - which is most
    // of them.
    const widths = fitColumnWidths(cols, items, terminalWidth());
    const table = new Table({
      head: cols.map((c) => this.bold(c.header)),
      style: {
        head: [],
        border: [],
      },
      colAligns: cols.map((c) => c.align ?? DEFAULTS.UI.TABLE_ALIGN),
      ...(widths ? { colWidths: widths } : {}),
      wordWrap: true,
    });

    for (const item of items) {
      const row = cols.map((col) => {
        const value = item[col.key];
        if (col.format) {
          return col.format(value);
        }
        return formatValue(value);
      });
      table.push(row);
    }

    return table.toString();
  }

  formatCsv<T extends Record<string, unknown>>(data: T | T[], columns?: TableColumn[]): string {
    const items = Array.isArray(data) ? data : [data];
    if (items.length === 0) return '';

    const cols = columns ?? this.detectColumns(items);
    const lines: string[] = [];

    // Header row
    lines.push(cols.map((c) => escapeCSVValue(c.header)).join(','));

    // Data rows
    for (const item of items) {
      const row = cols.map((col) => {
        const value = item[col.key];
        return escapeCSVValue(formatValue(value));
      });
      lines.push(row.join(','));
    }

    return lines.join('\n');
  }

  // Convenience methods for colored output (stderr to avoid polluting data output)
  success(message: string): void {
    if (this.state.quiet) return;
    this.writeProse(message, (line) => (this.colorEnabled ? chalk.green(line) : line));
  }

  error(message: string): void {
    this.writeProse(message, (line) => (this.colorEnabled ? chalk.red(line) : line));
  }

  warn(message: string): void {
    this.state.warnings.push(message);
    if (this.state.quiet) return;
    this.writeProse(message, (line) => (this.colorEnabled ? chalk.yellow(line) : line));
  }

  info(message: string): void {
    if (this.state.quiet) return;
    // chalk.blueBright (ANSI 12) reads cleanly on both light and dark
    // terminal backgrounds. The default chalk.blue (ANSI 4) renders as a
    // dark navy on standard 16-color palettes and was reported unreadable
    // against black backgrounds (see `rdc repo template list` output).
    this.writeProse(message, (line) => (this.colorEnabled ? chalk.blueBright(line) : line));
  }

  dim(text: string): string {
    return this.colorEnabled ? chalk.dim(text) : text;
  }

  bold(text: string): string {
    return this.colorEnabled ? chalk.bold(text) : text;
  }

  print(data: unknown, format: OutputFormat = 'table'): void {
    if (typeof data === 'string') {
      this.writeOut(data);
      return;
    }

    const output = this.format(data as Record<string, unknown> | Record<string, unknown>[], format);
    this.writeOut(output);
  }

  private detectColumns<T extends Record<string, unknown>>(items: T[]): TableColumn[] {
    if (items.length === 0) return [];

    const keys = Object.keys(items[0]);
    return keys.map((key) => {
      const column: TableColumn = {
        key,
        header: formatPropertyName(key),
      };

      // Auto-format timestamp columns
      if (this.isTimestampKey(key)) {
        column.format = (value) => formatTimestampAsIs(value as string, 'datetime');
      }

      return column;
    });
  }

  private isTimestampKey(key: string): boolean {
    const lowerKey = key.toLowerCase();
    return (
      lowerKey.includes('time') ||
      lowerKey.includes('date') ||
      lowerKey.endsWith('at') ||
      lowerKey === 'created' ||
      lowerKey === 'updated' ||
      lowerKey === 'timestamp'
    );
  }
}

export const outputService = new OutputService();
