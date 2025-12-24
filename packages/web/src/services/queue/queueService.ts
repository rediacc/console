import { type QueueMonitoringEvent, QueueService } from '@/platform/services/queue';
import type { QueueRequestContext } from '@/platform/types';
import { showMessage } from '@/utils/messages';
import { queueMonitoringService } from './queueMonitoringService';

const coreQueueService = new QueueService({
  emitNotification: ({ level, message }) => {
    showMessage(level, message);
  },
  emitMonitoringEvent: (event: QueueMonitoringEvent) => {
    if (event.type === 'task-start') {
      queueMonitoringService.addTask(
        event.taskId,
        event.data.teamName,
        event.data.machineName ?? '',
        'PENDING',
        undefined,
        undefined,
        event.data.bridgeName,
        event.data.priority
      );
    } else if (event.type === 'task-status') {
      queueMonitoringService.handleStatusUpdate(event.taskId, event.status);
    }
  },
});

queueMonitoringService.registerStatusHandler((taskId, status) => {
  coreQueueService.updateTaskStatus(taskId, status);
});

export const queueService = coreQueueService;
export type { QueueRequestContext };
