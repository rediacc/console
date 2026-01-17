/**
 * Shared utilities for Rediacc Console
 * Platform-agnostic functions that work in both web and CLI environments
 */

// CSV utilities
export { buildCSVContent, escapeCSVValue } from './csv';
// Text formatting
export { unescapeLogOutput } from './format';
export type { LogLevel, ParsedLogLine } from './logParser';
// Log parsing
export { parseLogLevel, parseLogLine, parseLogOutput } from './logParser';
// Property normalization
export { normalizeToBoolean, normalizeToNumber, normalizeToString } from './normalize';
// Progress parsing
export { extractMostRecentProgress, extractProgressMessage } from './progress';
// Search utilities
export { searchInFields } from './search';
// Size parsing utilities
export { calculateResourcePercent, parseMemorySize } from './size';
// Sorting utilities
export {
  compareValues,
  createArrayLengthSorter,
  createCustomSorter,
  createDateSorter,
  createSorter,
} from './sorting';
export type { SSHTestResult } from './sshTestResult';
// SSH test parsing
export { parseSshTestResult } from './sshTestResult';
