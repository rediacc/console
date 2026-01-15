import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import { Alert } from 'antd';
import React from 'react';
import { normalizeToNumber, normalizeToString } from '@/platform';
import { CloseCircleOutlined, RetweetOutlined } from '@/utils/optimizedIcons';

interface FailureReasonAlertProps {
  queueDetails: GetTeamQueueItems_ResultSet1 | null | undefined;
}

export const FailureReasonAlert: React.FC<FailureReasonAlertProps> = ({ queueDetails }) => {
  if (!queueDetails) return null;

  const lastFailureReason = normalizeToString(
    queueDetails,
    'lastFailureReason',
    'LastFailureReason'
  );
  const status = normalizeToString(queueDetails, 'status', 'Status');
  const retryCount = normalizeToNumber(queueDetails, 0, 'retryCount', 'RetryCount');

  // Don't show if no failure reason or if cancelling
  if (!lastFailureReason || status === 'CANCELLING') {
    return null;
  }

  const isPendingRetry = status === 'PENDING' && retryCount > 0;
  const maxRetriesReached = retryCount >= 2;

  const getMessage = () => {
    if (isPendingRetry) {
      return maxRetriesReached ? 'Task Failed - Max Retries Reached' : 'Task Failed - Retrying';
    }
    return 'Task Failed';
  };

  const getType = () => {
    if (isPendingRetry) {
      return maxRetriesReached ? 'error' : 'warning';
    }
    return 'error';
  };

  const getIcon = () => {
    if (isPendingRetry) {
      return maxRetriesReached ? <CloseCircleOutlined /> : <RetweetOutlined />;
    }
    return undefined;
  };

  return (
    <Alert
      data-testid="queue-trace-alert-failure"
      message={getMessage()}
      description={lastFailureReason}
      type={getType()}
      icon={getIcon()}
    />
  );
};
