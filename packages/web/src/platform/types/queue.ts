import type { VaultContextData } from './vault';

// Re-export types from shared package for backward compatibility
export type { FunctionRequirements, QueueRequestContext } from '@rediacc/shared/queue-vault';
// Re-export LocalQueueItem as QueueItem for backward compatibility in the platform layer
// This is the client-side queue item type (different from types/domain.ts QueueItem which is server-side)
export type {
  ActiveTask,
  LocalQueueItem as QueueItem,
  QueueItemData,
  QueueItemStatus,
} from '@rediacc/shared/services/queue';

/**
 * Queue vault payload (uses local VaultContextData type)
 */
export interface QueueVaultPayload {
  function: string;
  machine: string;
  team: string;
  params: Record<string, unknown>;
  contextData: VaultContextData;
}
