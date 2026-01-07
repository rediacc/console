/**
 * Log formatting utilities for CLI display
 * Parses and formats structured logs (logrus format) for terminal output
 */

import chalk from 'chalk';
import type { LogLevel, ParsedLogLine } from '@rediacc/shared/utils';

/**
 * Get chalk color function for log level
 */
function getLevelColor(level: LogLevel): (text: string) => string {
  switch (level) {
    case 'error':
      return chalk.red;
    case 'warning':
      return chalk.yellow;
    case 'info':
      return chalk.blue;
    case 'debug':
      return chalk.gray;
    default:
      return chalk.white;
  }
}

/**
 * Format ISO timestamp to YYYY-MM-DD HH:MM:SS for display
 */
function formatTime(timestamp?: string): string {
  if (!timestamp) return chalk.dim('---------- --:--:--');
  try {
    const date = new Date(timestamp);
    return chalk.dim(
      date.toLocaleString(undefined, {
        hour12: false,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    );
  } catch {
    return chalk.dim(timestamp);
  }
}

/**
 * Format log level as a colored badge
 */
function formatLevel(level: LogLevel): string {
  const color = getLevelColor(level);
  const label = level.toUpperCase().padEnd(7);
  return color(label);
}

/**
 * Format extras as key=value pairs
 */
function formatExtras(extras?: Record<string, string>): string {
  if (!extras || Object.keys(extras).length === 0) return '';
  const pairs = Object.entries(extras)
    .map(([key, value]) => chalk.dim(`${key}=${value}`))
    .join(' ');
  return ` ${pairs}`;
}

/**
 * Format a single parsed log line for CLI output
 */
function formatLogLine(entry: ParsedLogLine): string {
  if (entry.isStructured) {
    const time = formatTime(entry.time);
    const level = formatLevel(entry.level);
    const message = entry.message;
    const extras = formatExtras(entry.extras);
    return `${time}  ${level}  ${message}${extras}`;
  }

  // Plain text line - just show the message
  return `${chalk.dim('--:--:--')}  ${chalk.dim('       ')}  ${entry.message}`;
}

/**
 * Format parsed log entries for CLI display
 * Returns a formatted string with all log lines
 */
export function formatLogOutput(entries: ParsedLogLine[]): string {
  if (entries.length === 0) {
    return chalk.dim('No log output');
  }

  const lines = entries.map(formatLogLine);
  return lines.join('\n');
}

/**
 * Print log output header
 */
export function getLogHeader(): string {
  return chalk.bold(`${chalk.dim('Date/Time'.padEnd(22))}${chalk.dim('Level'.padEnd(9))}Message`);
}
