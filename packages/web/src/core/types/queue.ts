import type { VaultContextData } from './vault';

// Re-export types from shared package for backward compatibility
export type { QueueRequestContext, FunctionRequirements } from '@rediacc/shared/queue-vault';

export type QueueItemStatus =
  | 'pending'
  | 'submitting'
  | 'submitted'
  | 'failed'
  | 'cancelled'
  | 'completed';

export interface QueueItemData {
  teamName: string;
  machineName?: string;
  bridgeName?: string;
  queueVault: string;
  priority?: number;
}

export interface QueueItem {
  id: string;
  data: QueueItemData;
  retryCount: number;
  status: QueueItemStatus;
  timestamp: number;
  submitFunction: (data: QueueItemData) => Promise<unknown>;
  taskId?: string;
}

export interface ActiveTask {
  bridgeName: string;
  machineName: string;
  taskId: string;
  priority: number;
  status: 'pending' | 'assigned' | 'processing';
  timestamp: number;
}

export interface QueueVaultPayload {
  function: string;
  machine: string;
  team: string;
  params: Record<string, unknown>;
  contextData: VaultContextData;
}
