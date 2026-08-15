/**
 * Shared utilities for Rediacc Console
 * Platform-agnostic functions that work in both web and CLI environments
 */

// CSV utilities
export { buildCSVContent, escapeCSVValue } from './csv.js';
// Text formatting
export { unescapeLogOutput } from './format.js';
export type { LogLevel, ParsedLogLine } from './logParser.js';
// Log parsing
export { parseLogLevel, parseLogLine, parseLogOutput } from './logParser.js';
// Property normalization
export { normalizeToBoolean, normalizeToNumber, normalizeToString } from './normalize.js';
// Progress parsing
export { extractMostRecentProgress, extractProgressMessage } from './progress.js';
// Search utilities
export { searchInFields } from './search.js';
// Size parsing utilities
export { calculateResourcePercent, parseMemorySize } from './size.js';
// Sorting utilities
export {
  compareValues,
  createArrayLengthSorter,
  createCustomSorter,
  createDateSorter,
  createSorter,
} from './sorting.js';
export type { SSHTestResult } from './sshTestResult.js';
// SSH test parsing
export { parseSshTestResult } from './sshTestResult.js';
// Version comparison
export { compareVersions, isValidVersion, InvalidVersionError } from './version.js';
