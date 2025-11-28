# @rediacc/error-parser

Platform-agnostic error parsing utilities for Rediacc queue failures.

## Overview

This package provides comprehensive error parsing functionality for Rediacc's queue system. It parses severity-prefixed error messages, prioritizes errors by severity, and offers flexible formatting options for both web and CLI platforms.

## Features

- Parse severity-prefixed errors (CRITICAL:, ERROR:, WARNING:, INFO:)
- Extract single or multiple errors from command output
- Prioritize errors by severity level
- Platform-agnostic formatting with optional color functions
- TypeScript support with full type definitions
- Dual build (CommonJS + ESM)

## Installation

```bash
npm install @rediacc/error-parser
```

## Usage

### Basic Error Parsing

```typescript
import { parseFailureReason, extractFirstError, extractAllErrors } from '@rediacc/error-parser'

// Parse failure reason from queue
const output = "ERROR: Repository not found\nWARNING: Disk space low"
const result = parseFailureReason(output)

console.log(result.primaryError)
// { severity: 'ERROR', message: 'Repository not found', fullLine: '...' }

console.log(result.allErrors.length)
// 2

// Extract first error only
const firstError = extractFirstError(output)

// Extract all errors
const allErrors = extractAllErrors(output)
```

### Platform-Specific Formatting

#### Web (React + Ant Design)

```typescript
import { formatError, getSeverityLevel } from '@rediacc/error-parser'

function getSeverityColor(severity: ErrorSeverity): string {
  const level = getSeverityLevel(severity)
  const colorMap = {
    'critical': 'red',
    'error': 'error',
    'warning': 'warning',
    'info': 'blue',
    'default': 'default'
  }
  return colorMap[level] || 'default'
}
```

#### CLI (Chalk)

```typescript
import { formatError, formatErrors, getSeverityLevel } from '@rediacc/error-parser'
import chalk from 'chalk'

function chalkColorFn(text: string, level: string): string {
  const colorMap = {
    'critical': chalk.red.bold(text),
    'error': chalk.red(text),
    'warning': chalk.yellow(text),
    'info': chalk.blue(text),
    'default': chalk.gray(text)
  }
  return colorMap[level] || chalk.gray(text)
}

// Format single error with colors
const formatted = formatError(error, chalkColorFn)

// Format all errors with colors
const allFormatted = formatErrors(result, { showAll: true, colorFn: chalkColorFn })
```

## API Reference

### Types

#### `ErrorSeverity`
```typescript
type ErrorSeverity = 'CRITICAL' | 'ERROR' | 'WARNING' | 'INFO' | 'UNKNOWN'
```

#### `ParsedError`
```typescript
interface ParsedError {
  severity: ErrorSeverity
  message: string
  fullLine: string
}
```

#### `ParsedErrorResult`
```typescript
interface ParsedErrorResult {
  allErrors: ParsedError[]
  primaryError: ParsedError | null
}
```

### Functions

#### `parseFailureReason(failureReason: string | null | undefined): ParsedErrorResult`
Primary parser that extracts all severity-prefixed errors and selects the highest priority error.

#### `extractFirstError(output: string | null | undefined): ParsedError | null`
Extracts the first severity-prefixed error. Falls back to searching for "error" or "failed" keywords.

#### `extractAllErrors(output: string | null | undefined): ParsedError[]`
Extracts all severity-prefixed errors from the output.

#### `getSeverityLevel(severity: ErrorSeverity): string`
Maps severity to generic level strings for platform-specific coloring.

#### `formatError(error: ParsedError, colorFn?: Function): string`
Formats a single error with optional color function.

#### `formatErrors(result: ParsedErrorResult, options?: Object): string`
Formats errors from ParsedErrorResult with options for showing all errors and applying colors.

### Constants

#### `SEVERITY_PATTERNS`
Regex patterns for each severity level.

#### `SEVERITY_HIERARCHY`
Priority order mapping (lower number = higher priority).

#### `SEVERITY_REGEX`
Main regex for extracting severity-prefixed lines.

## Error Severity Hierarchy

Errors are prioritized in this order (highest to lowest):

1. CRITICAL
2. ERROR
3. WARNING
4. INFO
5. UNKNOWN

## License

MIT
