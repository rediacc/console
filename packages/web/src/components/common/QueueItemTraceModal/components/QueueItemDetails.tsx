import React from 'react';
import { Descriptions, Tag, Typography } from 'antd';
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

  const getStatusColor = () => {
    if (status === 'COMPLETED') return 'success';
    if (status === 'CANCELLED' || status === 'FAILED') return 'error';
    if (status === 'CANCELLING') return 'warning';
    if (status === 'PROCESSING' || status === 'ASSIGNED') return 'processing';
    return 'default';
  };

  return (
    <Descriptions column={2} size="small">
      <Descriptions.Item label="Task ID">
        <Typography.Text code>
          {normalizeToString(queueDetails, 'taskId', 'TaskId')}
        </Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label="Status">
        <Tag color={getStatusColor()}>{status}</Tag>
      </Descriptions.Item>
      <Descriptions.Item label="Priority">{queueDetails.priorityLabel || '-'}</Descriptions.Item>
      <Descriptions.Item label="Machine">
        <Typography.Text>{queueDetails.machineName}</Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label="Team">
        <Typography.Text>{queueDetails.teamName}</Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label="Bridge">
        <Typography.Text>{queueDetails.bridgeName}</Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label="Region">
        <Typography.Text>{queueDetails.regionName}</Typography.Text>
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
        <Tag color={retryCount === 0 ? 'success' : retryCount < 3 ? 'warning' : 'error'}>
          {retryCount}/2
        </Tag>
      </Descriptions.Item>
      {lastFailureReason && (
        <Descriptions.Item label="Last Failure Reason" span={2}>
          <Typography.Text type="warning">{lastFailureReason}</Typography.Text>
        </Descriptions.Item>
      )}
    </Descriptions>
  );
};
