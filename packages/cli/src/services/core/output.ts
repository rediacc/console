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

  getOperationDurationMs(): number | null {
    return this.state.operationDurationMs;
  }

  /** Mark that a timeline was rendered — suppresses the postAction "Completed" line */
  setTimelineRendered(): void {
    this.state.timelineRendered = true;
  }

  isTimelineRendered(): boolean {
    return this.state.timelineRendered;
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
    const table = new Table({
      head: cols.map((c) => this.bold(c.header)),
      style: {
        head: [],
        border: [],
      },
      colAligns: cols.map((c) => c.align ?? DEFAULTS.UI.TABLE_ALIGN),
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
    this.writeErr(this.colorEnabled ? chalk.green(message) : message);
  }

  error(message: string): void {
    this.writeErr(this.colorEnabled ? chalk.red(message) : message);
  }

  warn(message: string): void {
    this.state.warnings.push(message);
    if (this.state.quiet) return;
    this.writeErr(this.colorEnabled ? chalk.yellow(message) : message);
  }

  info(message: string): void {
    if (this.state.quiet) return;
    // chalk.blueBright (ANSI 12) reads cleanly on both light and dark
    // terminal backgrounds. The default chalk.blue (ANSI 4) renders as a
    // dark navy on standard 16-color palettes and was reported unreadable
    // against black backgrounds (see `rdc repo template list` output).
    this.writeErr(this.colorEnabled ? chalk.blueBright(message) : message);
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
