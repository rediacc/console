import React from 'react';
import { Descriptions } from 'antd';
import { RediaccTag, RediaccText } from '@/components/ui';
import {
  normalizeToNumber,
  normalizeToString,
  formatTimestampAsIs,
  formatDurationFull,
} from '@/platform';
import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';

interface QueueItemDetailsProps {
  queueDetails: GetTeamQueueItems_ResultSet1;
  totalDurationSeconds: number;
  processingDurationSeconds: number;
}

export const QueueItemDetails: React.FC<QueueItemDetailsProps> = ({
  queueDetails,
  totalDurationSeconds,
  processingDurationSeconds,
}) => {
  const status = normalizeToString(queueDetails, 'status', 'Status');
  const retryCount = normalizeToNumber(queueDetails, 0, 'retryCount', 'RetryCount');
  const lastFailureReason = normalizeToString(
    queueDetails,
    'lastFailureReason',
    'LastFailureReason'
  );

  const getStatusVariant = () => {
    if (status === 'COMPLETED') return 'success';
    if (status === 'CANCELLED' || status === 'FAILED') return 'error';
    if (status === 'CANCELLING') return 'warning';
    if (status === 'PROCESSING' || status === 'ASSIGNED') return 'primary';
    return 'neutral';
  };

  return (
    <Descriptions column={2} size="small">
      <Descriptions.Item label="Task ID">
        <RediaccText code>{normalizeToString(queueDetails, 'taskId', 'TaskId')}</RediaccText>
      </Descriptions.Item>
      <Descriptions.Item label="Status">
        <RediaccTag variant={getStatusVariant()}>{status}</RediaccTag>
      </Descriptions.Item>
      <Descriptions.Item label="Priority">{queueDetails.priorityLabel || '-'}</Descriptions.Item>
      <Descriptions.Item label="Machine">
        <RediaccText>{queueDetails.machineName}</RediaccText>
      </Descriptions.Item>
      <Descriptions.Item label="Team">
        <RediaccText>{queueDetails.teamName}</RediaccText>
      </Descriptions.Item>
      <Descriptions.Item label="Bridge">
        <RediaccText>{queueDetails.bridgeName}</RediaccText>
      </Descriptions.Item>
      <Descriptions.Item label="Region">
        <RediaccText>{queueDetails.regionName}</RediaccText>
      </Descriptions.Item>
      <Descriptions.Item label="Created">
        {formatTimestampAsIs(queueDetails.createdTime, 'datetime')}
      </Descriptions.Item>
      {queueDetails.assignedTime && (
        <Descriptions.Item label="Assigned">
          {formatTimestampAsIs(queueDetails.assignedTime, 'datetime')}
        </Descriptions.Item>
      )}
      {queueDetails.lastRetryAt && (
        <Descriptions.Item label="Last Retry">
          {formatTimestampAsIs(queueDetails.lastRetryAt, 'datetime')}
        </Descriptions.Item>
      )}
      <Descriptions.Item label="Total Duration">
        {formatDurationFull(totalDurationSeconds)}
      </Descriptions.Item>
      {processingDurationSeconds > 0 && (
        <Descriptions.Item label="Processing Duration">
          {formatDurationFull(processingDurationSeconds)}
        </Descriptions.Item>
      )}
      <Descriptions.Item label="Created By">
        {normalizeToString(queueDetails, 'createdBy', 'CreatedBy') || '-'}
      </Descriptions.Item>
      <Descriptions.Item label="Retry Count">
        <RediaccTag variant={retryCount === 0 ? 'success' : retryCount < 3 ? 'warning' : 'error'}>
          {retryCount}/2
        </RediaccTag>
      </Descriptions.Item>
      {lastFailureReason && (
        <Descriptions.Item label="Last Failure Reason" span={2}>
          <RediaccText color="warning">{lastFailureReason}</RediaccText>
        </Descriptions.Item>
      )}
    </Descriptions>
  );
};
