// Types

// Re-export types from shared packages
export type { ErrorSeverity, ParsedError, ParsedErrorResult } from '@rediacc/shared/error-parser';
export { parseFailureReason } from '@rediacc/shared/error-parser';

// Re-export functions from shared packages
export { formatAge, formatDurationFull, formatTimestampAsIs } from '@rediacc/shared/formatters';

export type {
  PriorityConfig,
  QueueHealthStatus,
  QueueStatus,
  StatusConfig,
} from '@rediacc/shared/queue';
export {
  filterActiveItems,
  filterCancelledItems,
  filterCompletedItems,
  filterFailedItems,
  STALE_TASK_CONSTANTS,
} from '@rediacc/shared/queue';
// Services - re-exported from shared (machine and repository are fully platform-agnostic)
export * from '@rediacc/shared/services/machine';
export * from '@rediacc/shared/services/repository';
// Re-export shared utilities
export {
  buildCSVContent,
  calculateResourcePercent,
  createArrayLengthSorter,
  createCustomSorter,
  createDateSorter,
  createSorter,
  extractMostRecentProgress,
  extractProgressMessage,
  normalizeToBoolean,
  normalizeToNumber,
  normalizeToString,
  searchInFields,
} from '@rediacc/shared/utils';

// Queue service - uses local wrapper with browser timer provider
export * from './services/queue';
export * from './types';

// Local utilities (not yet in shared)
export * from './utils/action-mapping';
export * from './utils/array';
export * from './utils/crypto';
export * from './utils/encoding';
export * from './utils/export';
export * from './utils/formValidation';
export * from './utils/json';
