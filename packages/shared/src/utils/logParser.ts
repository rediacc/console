/**
 * Log parser utility for parsing logrus-formatted log output
 * Used by StructuredLogView to display logs in a structured table/list format
 */

import { unescapeLogOutput } from './format';

export type LogLevel = 'info' | 'warning' | 'error' | 'debug';

export interface ParsedLogLine {
  /** Line index in original output */
  index: number;
  /** Original raw line text */
  raw: string;
  /** Function name prefix (e.g., "repository_create") */
  prefix?: string;
  /** Parsed timestamp if present */
  time?: string;
  /** Log level (defaults to 'info') */
  level: LogLevel;
  /** Main message text */
  message: string;
  /** Additional key=value pairs */
  extras?: Record<string, string>;
  /** Whether this line is structured (has time/level/msg fields) */
  isStructured: boolean;
}

// Regex patterns
const PREFIX_PATTERN = /^\[([^\]]+)\]\s*/;
const TIME_PATTERN = /time="([^"]+)"/;
const LEVEL_PATTERN = /level=(\w+)/;
const MSG_PATTERN = /msg="([^"]*)"/;

/**
 * Parse a log level string to a normalized LogLevel
 */
export function parseLogLevel(level: string): LogLevel {
  const normalized = level.toLowerCase();
  switch (normalized) {
    case 'debug':
      return 'debug';
    case 'info':
      return 'info';
    case 'warn':
    case 'warning':
      return 'warning';
    case 'error':
    case 'fatal':
    case 'panic':
      return 'error';
    default:
      return 'info';
  }
}

/**
 * Extract key=value pairs from log line content
 * Handles both quoted values (key="value") and unquoted values (key=value)
 */
function extractExtras(content: string): Record<string, string> | undefined {
  const extras: Record<string, string> = {};
  // Match key=value or key="value" patterns
  const kvPattern = /(\w+)=(?:"([^"]*)"|(\S+))/g;
  let match;

  while ((match = kvPattern.exec(content)) !== null) {
    const key = match[1];
    const value = match[2] || match[3];
    // Skip time, level, msg - they're handled separately
    if (!['time', 'level', 'msg'].includes(key)) {
      extras[key] = value;
    }
  }

  return Object.keys(extras).length > 0 ? extras : undefined;
}

/**
 * Parse a single log line into a structured ParsedLogLine object
 */
export function parseLogLine(line: string, index: number): ParsedLogLine {
  const trimmedLine = line.trim();

  // Empty line
  if (!trimmedLine) {
    return {
      index,
      raw: line,
      level: 'info',
      message: '',
      isStructured: false,
    };
  }

  // Extract prefix [function_name]
  const prefixMatch = PREFIX_PATTERN.exec(trimmedLine);
  const prefix = prefixMatch ? prefixMatch[1] : undefined;
  const content = prefixMatch ? trimmedLine.slice(prefixMatch[0].length) : trimmedLine;

  // Check for structured log format
  const timeMatch = TIME_PATTERN.exec(content);
  const levelMatch = LEVEL_PATTERN.exec(content);
  const msgMatch = MSG_PATTERN.exec(content);

  // Structured log line (has both time and level)
  if (timeMatch && levelMatch) {
    return {
      index,
      raw: line,
      prefix,
      time: timeMatch[1],
      level: parseLogLevel(levelMatch[1]),
      message: msgMatch ? msgMatch[1] : content,
      extras: extractExtras(content),
      isStructured: true,
    };
  }

  // Plain text line
  return {
    index,
    raw: line,
    prefix,
    level: 'info',
    message: content,
    isStructured: false,
  };
}

/**
 * Parse complete log output into an array of ParsedLogLine objects
 * Handles escape sequences and filters empty lines
 */
export function parseLogOutput(content: string): ParsedLogLine[] {
  if (!content) {
    return [];
  }

  const unescaped = unescapeLogOutput(content);
  const lines = unescaped.split('\n');

  return lines
    .map((line, index) => parseLogLine(line, index))
    .filter((entry) => entry.message.length > 0 || entry.isStructured);
}
