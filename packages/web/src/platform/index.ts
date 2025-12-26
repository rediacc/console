// Types

// Re-export types from shared packages
export type { ErrorSeverity, ParsedError, ParsedErrorResult } from '@rediacc/shared/error-parser';
export { parseFailureReason } from '@rediacc/shared/error-parser';

// Re-export functions from shared packages
export { formatAge, formatTimestampAsIs, formatDurationFull } from '@rediacc/shared/formatters';

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

// Re-export shared utilities
export {
  normalizeToString,
  normalizeToNumber,
  normalizeToBoolean,
  buildCSVContent,
  extractMostRecentProgress,
  extractProgressMessage,
  createSorter,
  createDateSorter,
  createCustomSorter,
  createArrayLengthSorter,
  calculateResourcePercent,
  searchInFields,
} from '@rediacc/shared/utils';

// Services - re-exported from shared (machine and repository are fully platform-agnostic)
export * from '@rediacc/shared/services/machine';
export * from '@rediacc/shared/services/repository';

// Queue service - uses local wrapper with browser timer provider
export * from './services/queue';
export * from './types';

// Local utilities (not yet in shared)
export * from './utils/action-mapping';
export * from './utils/array';
export * from './utils/crypto';
export * from './utils/encoding';
export * from './utils/export';
export * from './utils/json';
export * from './utils/formValidation';
