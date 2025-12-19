import React from 'react';
import { Button } from 'antd';
import { RediaccAlert } from '@/components/ui';
import { normalizeToString } from '@/platform';
import {
  ClockCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import type { TaskStalenessLevel } from '../types';


interface StaleTaskWarningProps {
  taskStaleness: TaskStalenessLevel;
  queueDetails: GetTeamQueueItems_ResultSet1 | null | undefined;
  isCancelling: boolean;
  onCancel: () => void;
}

export const StaleTaskWarning: React.FC<StaleTaskWarningProps> = ({
  taskStaleness,
  queueDetails,
  isCancelling,
  onCancel,
}) => {
  if (!queueDetails) return null;

  const status = normalizeToString(queueDetails, 'status', 'Status');
  const canBeCancelled = queueDetails.canBeCancelled;
  const isActive = status === 'PENDING' || status === 'ASSIGNED' || status === 'PROCESSING';

  // Cancelling status
  if (status === 'CANCELLING') {
    return (
      <RediaccAlert
        data-testid="queue-trace-alert-cancelling"
        message="Task Being Cancelled"
        description="The task is being cancelled. The bridge will stop execution gracefully."
        variant="warning"
        showIcon
        icon={<SyncOutlined spin />}
      />
    );
  }

  // Progressive staleness warnings
  if (taskStaleness === 'early') {
    return (
      <RediaccAlert
        data-testid="queue-trace-alert-early"
        message="Task May Be Inactive"
        description="Task hasn't provided updates for over 1 minute. This may be normal for long-running operations."
        variant="info"
        showIcon
        icon={<ClockCircleOutlined />}
        spacing="default"
      />
    );
  }

  if (taskStaleness === 'stale') {
    return (
      <RediaccAlert
        data-testid="queue-trace-alert-stale"
        message="Task May Be Stale"
        description="Task appears inactive for over 1.5 minutes. Consider canceling if no progress is expected."
        variant="warning"
        showIcon
        icon={<WarningOutlined />}
        action={
          canBeCancelled && isActive ? (
            <Button
              danger
              size="small"
              icon={<CloseCircleOutlined />}
              onClick={onCancel}
              loading={isCancelling}
            >
              Cancel Task
            </Button>
          ) : null
        }
        spacing="default"
      />
    );
  }

  if (taskStaleness === 'critical') {
    return (
      <RediaccAlert
        data-testid="queue-trace-alert-critical"
        message="Task Likely Stuck - Cancellation Recommended"
        description="Task has been inactive for over 2 minutes. The queue processor will automatically timeout this task at 3 minutes if no activity is detected."
        variant="error"
        showIcon
        icon={<ExclamationCircleOutlined />}
        action={
          canBeCancelled && isActive ? (
            <Button
              danger
              type="primary"
              icon={<CloseCircleOutlined />}
              onClick={onCancel}
              loading={isCancelling}
            >
              Cancel Stuck Task
            </Button>
          ) : null
        }
      />
    );
  }

  return null;
};
