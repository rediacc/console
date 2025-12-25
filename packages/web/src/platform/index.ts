// Types

// Re-export types from shared packages
export type { ErrorSeverity, ParsedError, ParsedErrorResult } from '@rediacc/shared/error-parser';
export { parseFailureReason } from '@rediacc/shared/error-parser';
// Re-export functions from shared packages
export { formatAge } from '@rediacc/shared/formatters';
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
// API utilities
// Services - re-exported from shared (machine and repository are fully platform-agnostic)
export * from '@rediacc/shared/services/machine';
export * from '@rediacc/shared/services/repository';
// Queue service - uses local wrapper with browser timer provider
export * from './services/queue';
export * from './types';
export * from './utils/action-mapping';
export * from './utils/array';
export * from './utils/crypto';
export * from './utils/encoding';
export * from './utils/export';
// Existing utilities
export * from './utils/json';
export * from './utils/normalize';
export * from './utils/progress-parser';
export * from './utils/search';
export * from './utils/size';
export * from './utils/sorting';
// New utilities
export * from './utils/time';
export * from './utils/formValidation';
