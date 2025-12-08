/**
 * Queue service types
 * Platform-agnostic types for queue state management
 */

// Re-export types from queue-vault for convenience
export type { FunctionRequirements, QueueRequestContext } from '../../queue-vault';

/**
 * Timer provider interface for platform-agnostic timer operations
 * Allows the queue service to work in both browser and Node.js environments
 */
export interface TimerProvider {
  setInterval: (callback: () => void, ms: number) => number | NodeJS.Timeout;
  clearInterval: (id: number | NodeJS.Timeout) => void;
  setTimeout: (callback: () => void, ms: number) => number | NodeJS.Timeout;
}

/**
 * Local queue item status (client-side state)
 * Different from QueueStatus in types/domain.ts which is for server-side items
 */
export type LocalQueueItemStatus =
  | 'pending'
  | 'submitting'
  | 'submitted'
  | 'failed'
  | 'cancelled'
  | 'completed';

/**
 * Data for a local queue item (client-side)
 */
export interface LocalQueueItemData {
  teamName: string;
  machineName?: string;
  bridgeName?: string;
  queueVault: string;
  priority?: number;
}

/**
 * Local queue item (client-side state management)
 * Different from QueueItem in types/domain.ts which is the server-side representation
 */
export interface LocalQueueItem {
  id: string;
  data: LocalQueueItemData;
  retryCount: number;
  status: LocalQueueItemStatus;
  timestamp: number;
  submitFunction: (data: LocalQueueItemData) => Promise<unknown>;
  taskId?: string;
}

// Backward compatibility aliases
export type QueueItemStatus = LocalQueueItemStatus;
export type QueueItemData = LocalQueueItemData;
// Note: QueueItem is NOT aliased to avoid conflict with types/domain.ts

/**
 * Active task information
 */
export interface ActiveTask {
  bridgeName: string;
  machineName: string;
  taskId: string;
  priority: number;
  status: 'pending' | 'assigned' | 'processing';
  timestamp: number;
}

/**
 * Queue notification level
 */
export type QueueNotificationLevel = 'info' | 'success' | 'warning' | 'error';

/**
 * Queue notification
 */
export interface QueueNotification {
  level: QueueNotificationLevel;
  message: string;
}

/**
 * Queue monitoring event
 */
export type QueueMonitoringEvent =
  | { type: 'task-start'; taskId: string; data: LocalQueueItemData }
  | { type: 'task-status'; taskId: string; status: 'completed' | 'failed' | 'cancelled' };

/**
 * Configuration for QueueStateManager
 */
export interface QueueStateManagerConfig {
  /** Timer provider for setInterval/clearInterval */
  timer: TimerProvider;
  /** Whether running in extension context (delays initial processing) */
  isExtensionContext?: boolean;
  /** Notification callback */
  emitNotification?: (notification: QueueNotification) => void;
  /** Monitoring event callback */
  emitMonitoringEvent?: (event: QueueMonitoringEvent) => void;
}

/**
 * Configuration for QueueService
 */
export interface QueueServiceConfig {
  /** Function to get the API URL */
  getApiUrl: () => string;
  /** Base64 encoding function */
  encodeBase64: (value: string) => string;
  /** Timer provider for the state manager */
  timer: TimerProvider;
  /** Whether running in extension context */
  isExtensionContext?: boolean;
  /** Notification callback */
  emitNotification?: (notification: QueueNotification) => void;
  /** Monitoring event callback */
  emitMonitoringEvent?: (event: QueueMonitoringEvent) => void;
}

/**
 * Queue listener callback
 */
export type QueueListener = (queue: LocalQueueItem[]) => void;

/**
 * Queue item listener callback
 */
export type QueueItemListener = (item: LocalQueueItem | undefined) => void;
