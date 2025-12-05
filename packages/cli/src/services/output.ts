/* eslint-disable no-console */
import Table from 'cli-table3';
import chalk from 'chalk';
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
  private colorEnabled: boolean;

  constructor() {
    this.colorEnabled = !process.env.REDIACC_NO_COLOR && process.stdout.isTTY !== false;
  }

  format<T extends Record<string, unknown>>(
    data: T | T[],
    format: OutputFormat = 'table',
    columns?: TableColumn[]
  ): string {
    switch (format) {
      case 'json':
        return this.formatJson(data);
      case 'yaml':
        return this.formatYaml(data);
      case 'csv':
        return this.formatCsv(data, columns);
      case 'table':
      default:
        return this.formatTable(data, columns);
    }
  }

  formatJson<T>(data: T): string {
    return JSON.stringify(data, null, 2);
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
    const cols = columns || this.detectColumns(items);
    if (cols.length === 0) {
      return this.dim('No columns to display');
    }

    const table = new Table({
      head: cols.map((c) => this.bold(c.header)),
      style: {
        head: [],
        border: [],
      },
      colAligns: cols.map((c) => c.align || 'left'),
    });

    for (const item of items) {
      const row = cols.map((col) => {
        const value = item[col.key];
        if (col.format) {
          return col.format(value);
        }
        return this.formatValue(value);
      });
      table.push(row);
    }

    return table.toString();
  }

  formatCsv<T extends Record<string, unknown>>(data: T | T[], columns?: TableColumn[]): string {
    const items = Array.isArray(data) ? data : [data];
    if (items.length === 0) return '';

    const cols = columns || this.detectColumns(items);
    const lines: string[] = [];

    // Header row
    lines.push(cols.map((c) => this.escapeCsv(c.header)).join(','));

    // Data rows
    for (const item of items) {
      const row = cols.map((col) => {
        const value = item[col.key];
        return this.escapeCsv(this.formatValue(value));
      });
      lines.push(row.join(','));
    }

    return lines.join('\n');
  }

  // Convenience methods for colored output
  success(message: string): void {
    console.log(this.colorEnabled ? chalk.green(message) : message);
  }

  error(message: string): void {
    console.error(this.colorEnabled ? chalk.red(message) : message);
  }

  warn(message: string): void {
    console.warn(this.colorEnabled ? chalk.yellow(message) : message);
  }

  info(message: string): void {
    console.log(this.colorEnabled ? chalk.blue(message) : message);
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
    return keys.map((key) => ({
      key,
      header: this.formatHeader(key),
    }));
  }

  private formatHeader(key: string): string {
    // Convert camelCase/snake_case to Title Case
    return key
      .replace(/([A-Z])/g, ' $1')
      .replace(/_/g, ' ')
      .replace(/^\s+/, '')
      .split(' ')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  private formatValue(value: unknown): string {
    if (value === null || value === undefined) {
      return '';
    }
    if (typeof value === 'object') {
      return JSON.stringify(value);
    }
    return String(value);
  }

  private escapeCsv(value: string): string {
    if (value.includes(',') || value.includes('"') || value.includes('\n')) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  }
}

export const outputService = new OutputService();
export default outputService;
