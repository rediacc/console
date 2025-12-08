/**
 * Web queue service wrapper
 * Re-exports the shared QueueService with browser-specific configuration
 */

import { browserTimerProvider, isExtensionContext } from '@/platform/adapters/timer';
import { encodeBase64 } from '@/platform/utils/encoding';
import { QueueService as SharedQueueService } from '@rediacc/shared/services/queue';

// Re-export types from shared for backward compatibility
// Note: QueueItem is not exported from shared to avoid conflict with types/domain.ts
// Use LocalQueueItem from shared if you need the client-side queue item type
export type {
  ActiveTask,
  QueueItemData,
  QueueItemListener,
  QueueItemStatus,
  QueueListener,
  QueueMonitoringEvent,
  QueueNotification,
  QueueNotificationLevel,
} from '@rediacc/shared/services/queue';

/**
 * Queue service dependencies (for backward compatibility)
 */
export interface QueueServiceDependencies {
  emitNotification?: (
    notification: import('@rediacc/shared/services/queue').QueueNotification
  ) => void;
  emitMonitoringEvent?: (
    event: import('@rediacc/shared/services/queue').QueueMonitoringEvent
  ) => void;
}

/**
 * Browser-configured queue service
 * Uses window.location for API URL and browser timers
 */
export class QueueService extends SharedQueueService {
  constructor(dependencies: QueueServiceDependencies = {}) {
    super({
      getApiUrl: () => {
        if (typeof window !== 'undefined') {
          return `${window.location.origin}/api`;
        }
        return '';
      },
      encodeBase64,
      timer: browserTimerProvider,
      isExtensionContext: isExtensionContext(),
      emitNotification: dependencies.emitNotification,
      emitMonitoringEvent: dependencies.emitMonitoringEvent,
    });
  }
}
