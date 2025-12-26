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
