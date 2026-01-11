/**
 * Platform-agnostic error parsing utilities for Rediacc queue failures
 * Extracted from web console (source of truth)
 */

/**
 * Error severity levels for parsing queue errors
 */
export type ErrorSeverity = 'CRITICAL' | 'ERROR' | 'WARNING' | 'INFO' | 'UNKNOWN';

/**
 * Parsed error information from queue output
 */
export interface ParsedError {
  severity: ErrorSeverity;
  message: string;
  fullLine: string;
}

/**
 * Parsed error result with all errors and prioritization
 */
export interface ParsedErrorResult {
  /** All errors found in the text */
  allErrors: ParsedError[];
  /** The highest severity error (for display priority) */
  primaryError: ParsedError | null;
}

/**
 * Regex patterns for severity matching
 */
export const SEVERITY_PATTERNS = {
  CRITICAL: /^CRITICAL:/i,
  ERROR: /^ERROR:/i,
  WARNING: /^WARNING:/i,
  INFO: /^INFO:/i,
};

/**
 * Priority hierarchy (lower number = higher priority)
 */
export const SEVERITY_HIERARCHY: Record<ErrorSeverity, number> = {
  CRITICAL: 1,
  ERROR: 2,
  WARNING: 3,
  INFO: 4,
  UNKNOWN: 5,
};

/**
 * Main regex for extracting severity-prefixed lines
 */
export const SEVERITY_REGEX = /^(CRITICAL|ERROR|WARNING|INFO):\s*(.+)/i;

/**
 * Extract first error line from command output
 * Searches for lines with severity prefixes: CRITICAL:, ERROR:, WARNING:, INFO:
 *
 * @param output - Command output string to parse
 * @returns ParsedError object with severity and message, or null if no error found
 *
 * @example
 * const output = "Some output\nERROR: Repository not found\nMore output"
 * const error = extractFirstError(output)
 * // Returns: { severity: 'ERROR', message: 'Repository not found', fullLine: 'ERROR: Repository not found' }
 */
export function extractFirstError(output: string | null | undefined): ParsedError | null {
  if (!output) return null;

  // Split into lines and search for first line with severity prefix
  const lines = output.split('\n');
  const severityPattern = /^(CRITICAL|ERROR|WARNING|INFO):\s*(.+)$/;

  for (const line of lines) {
    const trimmedLine = line.trim();
    const match = severityPattern.exec(trimmedLine);

    if (match) {
      const [, severity, message] = match;
      return {
        severity: severity as ErrorSeverity,
        message: message.trim(),
        fullLine: trimmedLine,
      };
    }
  }

  // If no severity prefix found, look for lines containing "error" or "failed" (case-insensitive)
  for (const line of lines) {
    const trimmedLine = line.trim();
    const lowerLine = trimmedLine.toLowerCase();

    if (lowerLine.includes('error') || lowerLine.includes('failed')) {
      return {
        severity: 'UNKNOWN',
        message: trimmedLine,
        fullLine: trimmedLine,
      };
    }
  }

  return null;
}

/**
 * Extract all severity-prefixed lines from command output
 * Searches for ALL lines with severity prefixes: CRITICAL:, ERROR:, WARNING:, INFO:
 *
 * @param output - Command output string to parse
 * @returns Array of ParsedError objects, empty array if none found
 *
 * @example
 * const output = "Some output\nERROR: Repository not found\nWARNING: Disk space low\nMore output"
 * const errors = extractAllErrors(output)
 * // Returns: [
 * //   { severity: 'ERROR', message: 'Repository not found', fullLine: 'ERROR: Repository not found' },
 * //   { severity: 'WARNING', message: 'Disk space low', fullLine: 'WARNING: Disk space low' }
 * // ]
 */
export function extractAllErrors(output: string | null | undefined): ParsedError[] {
  if (!output) return [];

  const errors: ParsedError[] = [];
  const lines = output.split('\n');
  const severityPattern = /^(CRITICAL|ERROR|WARNING|INFO):\s*(.+)$/;

  for (const line of lines) {
    const trimmedLine = line.trim();
    const match = severityPattern.exec(trimmedLine);

    if (match) {
      const [, severity, message] = match;
      errors.push({
        severity: severity as ErrorSeverity,
        message: message.trim(),
        fullLine: trimmedLine,
      });
    }
  }

  return errors;
}

/**
 * Parse failure reason text to extract all severity-prefixed errors
 * This is the consolidated parsing logic used across the application
 *
 * @param failureReason - Text containing error messages (e.g., from lastFailureReason)
 * @returns ParsedErrorResult with all errors and the primary (highest severity) error
 *
 * @example
 * const text = "ERROR: Repository not found\nWARNING: Disk space low"
 * const result = parseFailureReason(text)
 * // Returns:
 * // {
 * //   allErrors: [
 * //     { severity: 'ERROR', message: 'Repository not found', ... },
 * //     { severity: 'WARNING', message: 'Disk space low', ... }
 * //   ],
 * //   primaryError: { severity: 'ERROR', message: 'Repository not found', ... }
 * // }
 */
export function parseFailureReason(failureReason: string | null | undefined): ParsedErrorResult {
  if (!failureReason) {
    return { allErrors: [], primaryError: null };
  }

  const errors: ParsedError[] = [];
  const lines = failureReason.split('\n');
  const severityPattern = /^(CRITICAL|ERROR|WARNING|INFO):\s*(.+)$/;

  // Extract all severity-prefixed lines
  for (const line of lines) {
    const trimmedLine = line.trim();
    const match = severityPattern.exec(trimmedLine);

    if (match) {
      const [, severity, message] = match;
      errors.push({
        severity: severity as ErrorSeverity,
        message: message.trim(),
        fullLine: trimmedLine,
      });
    }
  }

  // If no severity-prefixed errors found, treat entire message as single unknown error
  if (errors.length === 0 && failureReason.trim()) {
    errors.push({
      severity: 'UNKNOWN',
      message: failureReason.trim(),
      fullLine: failureReason.trim(),
    });
  }

  // Find the highest severity error (CRITICAL > ERROR > WARNING > INFO > UNKNOWN)
  const primaryError =
    errors.length > 0
      ? errors.reduce((highest, current) => {
          const severityOrder: Record<ErrorSeverity, number> = {
            CRITICAL: 0,
            ERROR: 1,
            WARNING: 2,
            INFO: 3,
            UNKNOWN: 4,
          };
          const highestOrder = severityOrder[highest.severity];
          const currentOrder = severityOrder[current.severity];
          return currentOrder < highestOrder ? current : highest;
        })
      : null;

  return { allErrors: errors, primaryError };
}

/**
 * Maps ErrorSeverity to generic level strings for platform-specific coloring
 *
 * @param severity - Error severity level
 * @returns Generic level string ('critical', 'error', 'warning', 'info', 'default')
 *
 * @example
 * const level = getSeverityLevel('ERROR')
 * // Returns: 'error'
 */
export function getSeverityLevel(severity: ErrorSeverity): string {
  const levelMap: Record<ErrorSeverity, string> = {
    CRITICAL: 'critical',
    ERROR: 'error',
    WARNING: 'warning',
    INFO: 'info',
    UNKNOWN: 'default',
  };
  return levelMap[severity] || 'default';
}

/**
 * Platform-agnostic single error formatter
 * Accepts an optional color function to apply platform-specific styling
 *
 * @param error - Parsed error object
 * @param colorFn - Optional color function (text, level) => styledText
 * @returns Formatted error string
 *
 * @example
 * // Without color function
 * formatError(error)
 * // Returns: "[ERROR] Repository not found"
 *
 * // With color function (e.g., chalk in CLI)
 * formatError(error, (text, level) => chalk.red(text))
 * // Returns: colored "[ERROR] Repository not found"
 */
export function formatError(
  error: ParsedError,
  colorFn?: (text: string, level: string) => string
): string {
  const level = getSeverityLevel(error.severity);
  const prefix = `[${error.severity}]`;
  const message = error.message;

  if (colorFn) {
    return `${colorFn(prefix, level)} ${message}`;
  }
  return `${prefix} ${message}`;
}

/**
 * Platform-agnostic multi-error formatter
 * Accepts optional configuration for showing all errors and applying colors
 *
 * @param result - Parsed error result
 * @param options - Configuration options
 * @param options.showAll - If true, format all errors; if false, show only primary
 * @param options.colorFn - Optional color function (text, level) => styledText
 * @returns Formatted error string(s)
 *
 * @example
 * // Show only primary error
 * formatErrors(result)
 * // Returns: "[ERROR] Repository not found"
 *
 * // Show all errors with colors
 * formatErrors(result, { showAll: true, colorFn: chalkColorFn })
 * // Returns: "[ERROR] Repository not found\n[WARNING] Disk space low"
 */
export function formatErrors(
  result: ParsedErrorResult,
  options?: {
    showAll?: boolean;
    colorFn?: (text: string, level: string) => string;
  }
): string {
  const { showAll = false, colorFn } = options ?? {};

  if (showAll && result.allErrors.length > 0) {
    return result.allErrors.map((error) => formatError(error, colorFn)).join('\n');
  }

  if (result.primaryError) {
    return formatError(result.primaryError, colorFn);
  }

  return 'No errors found';
}
