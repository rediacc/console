// Types

// Re-export types from shared packages
export type { ErrorSeverity, ParsedError, ParsedErrorResult } from '@rediacc/shared/error-parser';
export {
  extractAllErrors,
  extractFirstError,
  parseFailureReason,
} from '@rediacc/shared/error-parser';
// Re-export functions from shared packages
export { formatAge } from '@rediacc/shared/formatters';
export type {
  PriorityConfig,
  QueueHealthStatus,
  QueueStatus,
  StatusConfig,
} from '@rediacc/shared/queue';
export {
  ACTIVE_STATUSES,
  filterActiveItems,
  filterCancelledItems,
  filterCompletedItems,
  filterFailedItems,
  getPriorityConfig,
  getSeverityColor,
  getStatusConfig,
  isActiveStatus,
  isPermanentFailure,
  isRetryEligible,
  isStaleTask,
  isTerminalStatus,
  PERMANENT_FAILURE_MESSAGES,
  PRIORITY_CONFIG,
  QUEUE_STATUS_CONFIG,
  STALE_TASK_CONSTANTS,
  TERMINAL_STATUSES,
} from '@rediacc/shared/queue';
// API utilities
// Services - re-exported from shared (machine and repo are fully platform-agnostic)
export * from '@rediacc/shared/services/machine';
export * from '@rediacc/shared/services/repo';
// Queue service - uses local wrapper with browser timer provider
export * from './services/queue';
export * from './types';
export * from './utils/action-mapping';
export * from './utils/array';
export type { BulkValidationResult as GenericBulkValidationResult } from './utils/batch';
// Re-export batch utils excluding BulkValidationResult to avoid conflict with shared/services/machine
export { type BulkValidationError, performBulkValidation } from './utils/batch';
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
export * from './utils/validation';
