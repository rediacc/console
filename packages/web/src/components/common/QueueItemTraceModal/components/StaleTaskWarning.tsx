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

interface AlertConfig {
  testId: string;
  titleKey: string;
  descriptionKey: string;
  type: 'info' | 'warning' | 'error';
  icon: React.ReactNode;
  showAction?: boolean;
  buttonType?: 'default' | 'primary';
  buttonTextKey?: string;
}

const ACTIVE_STATUSES = ['PENDING', 'ASSIGNED', 'PROCESSING'] as const;
type ActiveStatus = (typeof ACTIVE_STATUSES)[number];

const STALENESS_ALERT_CONFIG: Record<Exclude<TaskStalenessLevel, 'none'>, AlertConfig> = {
  early: {
    testId: 'queue-trace-alert-early',
    titleKey: 'trace.earlyStaleTitle',
    descriptionKey: 'trace.earlyStaleDescription',
    type: 'info',
    icon: <ClockCircleOutlined />,
  },
  stale: {
    testId: 'queue-trace-alert-stale',
    titleKey: 'trace.staleTitle',
    descriptionKey: 'trace.staleDescription',
    type: 'warning',
    icon: <WarningOutlined />,
    showAction: true,
    buttonType: 'default',
    buttonTextKey: 'trace.cancelTask',
  },
  critical: {
    testId: 'queue-trace-alert-critical',
    titleKey: 'trace.criticalTitle',
    descriptionKey: 'trace.criticalDescription',
    type: 'error',
    icon: <ExclamationCircleOutlined />,
    showAction: true,
    buttonType: 'primary',
    buttonTextKey: 'trace.cancelStuckTask',
  },
};

export const StaleTaskWarning: React.FC<StaleTaskWarningProps> = ({
  taskStaleness,
  queueDetails,
  isCancelling,
  onCancel,
}) => {
  const { t } = useTranslation('queue');

  if (!queueDetails) return null;

  const status = normalizeToString(queueDetails, 'status', 'Status');

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

  if (taskStaleness === 'none') return null;

  const config = STALENESS_ALERT_CONFIG[taskStaleness];
  const canBeCancelled = queueDetails.canBeCancelled;
  const isActive = ACTIVE_STATUSES.includes(status as ActiveStatus);
  const shouldShowAction = config.showAction && canBeCancelled && isActive;

  return (
    <Alert
      data-testid={config.testId}
      message={t(config.titleKey)}
      description={t(config.descriptionKey)}
      type={config.type}
      icon={config.icon}
      action={
        shouldShowAction ? (
          <Button
            danger
            size={config.buttonType === 'primary' ? undefined : 'small'}
            type={config.buttonType}
            icon={<CloseCircleOutlined />}
            onClick={onCancel}
            loading={isCancelling}
          >
            {t(config.buttonTextKey!)}
          </Button>
        ) : undefined
      }
    />
  );
};
