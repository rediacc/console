/**
 * Shared utilities for Rediacc Console
 * Platform-agnostic functions that work in both web and CLI environments
 */

// Property normalization
export { normalizeToString, normalizeToNumber, normalizeToBoolean } from './normalize';

// CSV utilities
export { escapeCSVValue, buildCSVContent } from './csv';

// Progress parsing
export { extractMostRecentProgress, extractProgressMessage } from './progress';

// Sorting utilities
export {
  compareValues,
  createSorter,
  createDateSorter,
  createCustomSorter,
  createArrayLengthSorter,
} from './sorting';

// Size parsing utilities
export { parseMemorySize, calculateResourcePercent } from './size';

// Search utilities
export { searchInFields } from './search';

// Text formatting
export { unescapeLogOutput } from './format';

// Log parsing
export { parseLogLine, parseLogOutput, parseLogLevel } from './logParser';
export type { ParsedLogLine, LogLevel } from './logParser';

// SSH test parsing
export { parseSshTestResult } from './sshTestResult';
export type { SSHTestResult } from './sshTestResult';
