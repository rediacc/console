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
export declare const SEVERITY_PATTERNS: {
    CRITICAL: RegExp;
    ERROR: RegExp;
    WARNING: RegExp;
    INFO: RegExp;
};
/**
 * Priority hierarchy (lower number = higher priority)
 */
export declare const SEVERITY_HIERARCHY: Record<ErrorSeverity, number>;
/**
 * Main regex for extracting severity-prefixed lines
 */
export declare const SEVERITY_REGEX: RegExp;
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
export declare function extractFirstError(output: string | null | undefined): ParsedError | null;
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
export declare function extractAllErrors(output: string | null | undefined): ParsedError[];
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
export declare function parseFailureReason(failureReason: string | null | undefined): ParsedErrorResult;
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
export declare function getSeverityLevel(severity: ErrorSeverity): string;
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
export declare function formatError(error: ParsedError, colorFn?: (text: string, level: string) => string): string;
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
export declare function formatErrors(result: ParsedErrorResult, options?: {
    showAll?: boolean;
    colorFn?: (text: string, level: string) => string;
}): string;
//# sourceMappingURL=index.d.ts.map