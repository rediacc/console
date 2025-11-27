/**
 * Error parsing utilities for queue failure messages
 * This is a standalone version that can be used by the CLI without importing from web core
 */

export type ErrorSeverity = 'CRITICAL' | 'ERROR' | 'WARNING' | 'INFO' | 'UNKNOWN'

export interface ParsedError {
  severity: ErrorSeverity
  message: string
  fullLine: string
}

export interface ParsedErrorResult {
  /** All errors found in the text */
  allErrors: ParsedError[]
  /** The highest severity error (for display priority) */
  primaryError: ParsedError | null
}

/**
 * Parse failure reason text to extract all severity-prefixed errors
 *
 * Searches for lines with severity prefixes: CRITICAL:, ERROR:, WARNING:, INFO:
 *
 * @param failureReason - Text containing error messages (e.g., from lastFailureReason)
 * @returns ParsedErrorResult with all errors and the primary (highest severity) error
 *
 * @example
 * ```typescript
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
 * ```
 */
export function parseFailureReason(failureReason: string | null | undefined): ParsedErrorResult {
  if (!failureReason) {
    return { allErrors: [], primaryError: null }
  }

  const errors: ParsedError[] = []
  const lines = failureReason.split('\n')
  const severityPattern = /^(CRITICAL|ERROR|WARNING|INFO):\s*(.+)$/

  // Extract all severity-prefixed lines
  for (const line of lines) {
    const trimmedLine = line.trim()
    const match = trimmedLine.match(severityPattern)

    if (match) {
      const [, severity, message] = match
      errors.push({
        severity: severity as ErrorSeverity,
        message: message.trim(),
        fullLine: trimmedLine
      })
    }
  }

  // If no severity-prefixed errors found, treat entire message as single unknown error
  if (errors.length === 0 && failureReason.trim()) {
    errors.push({
      severity: 'UNKNOWN',
      message: failureReason.trim(),
      fullLine: failureReason.trim()
    })
  }

  // Find the highest severity error (CRITICAL > ERROR > WARNING > INFO > UNKNOWN)
  const primaryError = errors.length > 0 ? errors.reduce((highest, current) => {
    const severityOrder: Record<ErrorSeverity, number> = {
      CRITICAL: 0,
      ERROR: 1,
      WARNING: 2,
      INFO: 3,
      UNKNOWN: 4
    }
    const highestOrder = severityOrder[highest.severity]
    const currentOrder = severityOrder[current.severity]
    return currentOrder < highestOrder ? current : highest
  }) : null

  return { allErrors: errors, primaryError }
}

/**
 * Format parsed error for CLI display
 *
 * @param error - Parsed error object
 * @param colorize - Whether to apply chalk colors (default: true)
 * @returns Formatted string for CLI output
 */
export function formatErrorForCLI(error: ParsedError, colorize: boolean = true): string {
  if (!colorize) {
    return `[${error.severity}] ${error.message}`
  }

  // Colors will be applied by the outputService in the CLI
  return `[${error.severity}] ${error.message}`
}

/**
 * Format all errors for CLI display
 *
 * @param result - Parsed error result
 * @param showAll - Whether to show all errors or just primary (default: false)
 * @returns Formatted string for CLI output
 */
export function formatErrorsForCLI(result: ParsedErrorResult, showAll: boolean = false): string {
  if (!result.primaryError) {
    return ''
  }

  if (!showAll || result.allErrors.length === 1) {
    return formatErrorForCLI(result.primaryError, false)
  }

  return result.allErrors
    .map(error => formatErrorForCLI(error, false))
    .join('\n')
}
