/* eslint-disable no-console */

import { DEFAULTS } from '@rediacc/shared/config';
import { formatPropertyName, formatTimestampAsIs, formatValue } from '@rediacc/shared/formatters';
import { escapeCSVValue } from '@rediacc/shared/utils';
import chalk from 'chalk';
import Table from 'cli-table3';
import { stringify as yamlStringify } from 'yaml';
import type { OutputFormat } from '../types/index.js';

interface TableColumn {
  key: string;
  header: string;
  width?: number;
  align?: 'left' | 'center' | 'right';
  format?: (value: unknown) => string;
}

class OutputService {
  private readonly colorEnabled: boolean;
  private _quiet = false;
  private _fields: string[] | null = null;
  private _commandName: string | null = null;
  private _startTime: number | null = null;
  private _warnings: string[] = [];
  private _operationDurationMs: number | null = null;
  private _timelineRendered = false;

  constructor() {
    this.colorEnabled = !process.env.REDIACC_NO_COLOR && process.stdout.isTTY !== false;
  }

  setQuiet(quiet: boolean): void {
    this._quiet = quiet;
  }

  setFields(fields: string): void {
    this._fields = fields.split(',').map((f) => f.trim());
  }

  setCommandContext(name: string, startTime: number): void {
    this._commandName = name;
    this._startTime = startTime;
    this._warnings = [];
  }

  getCommandName(): string | null {
    return this._commandName;
  }

  getWarnings(): string[] {
    return this._warnings;
  }

  getDurationMs(): number {
    return this._startTime ? Date.now() - this._startTime : 0;
  }

  setOperationDuration(ms: number): void {
    this._operationDurationMs = ms;
  }

  getOperationDurationMs(): number | null {
    return this._operationDurationMs;
  }

  /** Mark that a timeline was rendered — suppresses the postAction "Completed" line */
  setTimelineRendered(): void {
    this._timelineRendered = true;
  }

  isTimelineRendered(): boolean {
    return this._timelineRendered;
  }

  private applyFieldFilter<T extends Record<string, unknown>>(data: T | T[]): T | T[] {
    if (!this._fields) return data;
    const pick = (obj: T): T => {
      const result: Record<string, unknown> = {};
      for (const field of this._fields!) {
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
    const envelope = {
      success: true,
      command: this._commandName ?? DEFAULTS.TELEMETRY.UNKNOWN,
      data,
      errors: null,
      warnings: this._warnings,
      metrics: {
        duration_ms: this.getDurationMs(),
        ...(this._operationDurationMs != null && {
          operation_duration_ms: this._operationDurationMs,
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
    if (this._quiet) return;
    console.error(this.colorEnabled ? chalk.green(message) : message);
  }

  error(message: string): void {
    console.error(this.colorEnabled ? chalk.red(message) : message);
  }

  warn(message: string): void {
    this._warnings.push(message);
    if (this._quiet) return;
    console.error(this.colorEnabled ? chalk.yellow(message) : message);
  }

  info(message: string): void {
    if (this._quiet) return;
    console.error(this.colorEnabled ? chalk.blue(message) : message);
  }

  dim(text: string): string {
    return this.colorEnabled ? chalk.dim(text) : text;
  }

  bold(text: string): string {
    return this.colorEnabled ? chalk.bold(text) : text;
  }

  print(data: unknown, format: OutputFormat = 'table'): void {
    if (typeof data === 'string') {
      console.log(data);
      return;
    }

    const output = this.format(data as Record<string, unknown> | Record<string, unknown>[], format);
    console.log(output);
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
