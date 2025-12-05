// Types
export * from './types';

// Existing utilities
export * from './utils/json';
export * from './utils/validation';
export * from './utils/crypto';
export * from './utils/encoding';

// New utilities
export * from './utils/time';
export * from './utils/size';
export * from './utils/sorting';
export * from './utils/search';
export * from './utils/export';
export * from './utils/array';
export * from './utils/action-mapping';
// Re-export types from shared packages
export type { ErrorSeverity, ParsedError, ParsedErrorResult } from '@rediacc/shared/error-parser';

export type {
  QueueHealthStatus,
  QueueStatus,
  StatusConfig,
  PriorityConfig,
} from '@rediacc/shared/queue';
export {
  QUEUE_STATUS_CONFIG,
  PRIORITY_CONFIG,
  STALE_TASK_CONSTANTS,
  TERMINAL_STATUSES,
  ACTIVE_STATUSES,
  PERMANENT_FAILURE_MESSAGES,
  isTerminalStatus,
  isActiveStatus,
  isPermanentFailure,
  getStatusConfig,
  getPriorityConfig,
  isRetryEligible,
  isStaleTask,
  filterActiveItems,
  filterCompletedItems,
  filterFailedItems,
  filterCancelledItems,
  getSeverityColor,
} from '@rediacc/shared/queue';

// Re-export functions from shared packages
export { formatAge } from '@rediacc/shared/formatters';
export {
  extractFirstError,
  extractAllErrors,
  parseFailureReason,
} from '@rediacc/shared/error-parser';
export * from './utils/normalize';
export * from './utils/progress-parser';
export * from './utils/batch';

// API utilities
// Services
export * from './services/queue';
export * from './services/machine';
export * from './services/repo';

// Repo sub-services (promotion, deletion, fork operations, backup, orchestration)
export * from './services/repo/promotion';
export * from './services/repo/grand-deletion';
export * from './services/repo/fork-operations';
export * from './services/repo/backup-validation';
export * from './services/repo/orchestration';
