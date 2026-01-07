import React from 'react';
import { Alert, Button } from 'antd';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('queue');

  if (!queueDetails) return null;

  const status = normalizeToString(queueDetails, 'status', 'Status');
  const canBeCancelled = queueDetails.canBeCancelled;
  const isActive = status === 'PENDING' || status === 'ASSIGNED' || status === 'PROCESSING';

  // Cancelling status
  if (status === 'CANCELLING') {
    return (
      <Alert
        data-testid="queue-trace-alert-cancelling"
        message={t('trace.cancellingTitle')}
        description={t('trace.cancellingDescription')}
        type="warning"
        icon={<SyncOutlined spin />}
      />
    );
  }

  // Progressive staleness warnings
  if (taskStaleness === 'early') {
    return (
      <Alert
        data-testid="queue-trace-alert-early"
        message={t('trace.earlyStaleTitle')}
        description={t('trace.earlyStaleDescription')}
        type="info"
        icon={<ClockCircleOutlined />}
      />
    );
  }

  if (taskStaleness === 'stale') {
    return (
      <Alert
        data-testid="queue-trace-alert-stale"
        message={t('trace.staleTitle')}
        description={t('trace.staleDescription')}
        type="warning"
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
              {t('trace.cancelTask')}
            </Button>
          ) : null
        }
      />
    );
  }

  if (taskStaleness === 'critical') {
    return (
      <Alert
        data-testid="queue-trace-alert-critical"
        message={t('trace.criticalTitle')}
        description={t('trace.criticalDescription')}
        type="error"
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
              {t('trace.cancelStuckTask')}
            </Button>
          ) : null
        }
      />
    );
  }

  return null;
};
