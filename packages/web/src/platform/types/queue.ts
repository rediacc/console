import type { VaultContextData } from './vault';

// Re-export types from shared package for backward compatibility
export type { QueueRequestContext, FunctionRequirements } from '@rediacc/shared/queue-vault';
export type {
  QueueItemStatus,
  QueueItemData,
  QueueItem,
  ActiveTask,
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
