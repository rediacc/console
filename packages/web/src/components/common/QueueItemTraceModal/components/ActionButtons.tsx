import { Button } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { normalizeToBoolean, normalizeToNumber, normalizeToString } from '@/platform';
import { CloseCircleOutlined, ReloadOutlined, RetweetOutlined } from '@/utils/optimizedIcons';
import type { ActionButtonsProps } from '../types';

export const ActionButtons: React.FC<ActionButtonsProps> = ({
  queueDetails,
  isCancelling,
  isRetrying,
  isTraceLoading,
  taskStaleness,
  onCancel,
  onRetry,
  onRefresh,
  onClose,
}) => {
  const { t } = useTranslation('queue');
  const status = queueDetails ? normalizeToString(queueDetails, 'status', 'Status') : '';
  const retryCount = queueDetails
    ? normalizeToNumber(queueDetails, 0, 'retryCount', 'RetryCount')
    : 0;
  const permanentlyFailed = queueDetails
    ? normalizeToBoolean(queueDetails, 'permanentlyFailed', 'PermanentlyFailed')
    : false;
  const canBeCancelled = queueDetails?.canBeCancelled ?? false;

  const showCancelButton =
    queueDetails &&
    canBeCancelled &&
    (status === 'PENDING' || status === 'ASSIGNED' || status === 'PROCESSING');

  const showRetryButton =
    queueDetails && status === 'FAILED' && retryCount < 2 && !permanentlyFailed;

  return [
    // Show Cancel button for PENDING, ASSIGNED, or PROCESSING tasks that can be cancelled
    // Style and text vary based on staleness level
    showCancelButton ? (
      <Button
        key="cancel"
        data-testid="queue-trace-cancel-button"
        danger
        type={taskStaleness === 'critical' ? 'primary' : 'default'}
        icon={<CloseCircleOutlined />}
        onClick={onCancel}
        loading={isCancelling}
        className={(() => {
          if (taskStaleness === 'critical') return 'font-semibold text-sm';
          return 'font-medium text-xs';
        })()}
      >
        {(() => {
          if (taskStaleness === 'critical') return t('trace.cancelStuckTaskBtn');
          if (taskStaleness === 'stale') return t('trace.cancelTaskBtn');
          return t('trace.cancelBtn');
        })()}
      </Button>
    ) : null,
    // Show Retry button only for failed tasks that haven't reached max retries
    showRetryButton ? (
      <Button
        key="retry"
        data-testid="queue-trace-retry-button"
        danger
        icon={<RetweetOutlined />}
        onClick={onRetry}
        loading={isRetrying}
      >
        {t('trace.retryAgain')}
      </Button>
    ) : null,
    <Button
      key="refresh"
      data-testid="queue-trace-refresh-button"
      icon={<ReloadOutlined />}
      onClick={onRefresh}
      loading={isTraceLoading}
    >
      {t('trace.refresh')}
    </Button>,
    <Button key="close" data-testid="queue-trace-close-button" onClick={onClose}>
      {t('trace.close')}
    </Button>,
  ].filter(Boolean);
};
