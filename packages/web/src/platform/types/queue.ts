// Re-export types from shared package for backward compatibility
export type { QueueRequestContext } from '@rediacc/shared/queue-vault';
// Re-export LocalQueueItem as QueueItem for backward compatibility in the platform layer
// This is the client-side queue item type (different from types/domain.ts QueueItem which is server-side)
export type {
  LocalQueueItem as QueueItem,
  QueueItemData,
} from '@rediacc/shared/services/queue';
