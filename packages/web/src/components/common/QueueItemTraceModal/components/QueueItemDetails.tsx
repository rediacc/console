import React from 'react';
import { Descriptions, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  formatDurationFull,
  formatTimestampAsIs,
  normalizeToNumber,
  normalizeToString,
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
  const { t } = useTranslation('queue');
  const status = normalizeToString(queueDetails, 'status', 'Status');
  const retryCount = normalizeToNumber(queueDetails, 0, 'retryCount', 'RetryCount');
  const lastFailureReason = normalizeToString(
    queueDetails,
    'lastFailureReason',
    'LastFailureReason'
  );

  return (
    <Descriptions column={{ xs: 1, sm: 2 }} size="small">
      <Descriptions.Item label={t('trace.taskId')}>
        <Typography.Text code>
          {normalizeToString(queueDetails, 'taskId', 'TaskId')}
        </Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label={t('trace.status')}>
        <Tag>{status}</Tag>
      </Descriptions.Item>
      <Descriptions.Item label={t('trace.priority')}>
        {queueDetails.priorityLabel ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('trace.machine')}>
        <Typography.Text>{queueDetails.machineName}</Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label={t('trace.team')}>
        <Typography.Text>{queueDetails.teamName}</Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label={t('trace.bridge')}>
        <Typography.Text>{queueDetails.bridgeName}</Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label={t('trace.region')}>
        <Typography.Text>{queueDetails.regionName}</Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label={t('trace.created')}>
        {formatTimestampAsIs(queueDetails.createdTime, 'datetime')}
      </Descriptions.Item>
      {queueDetails.assignedTime && (
        <Descriptions.Item label={t('trace.assigned')}>
          {formatTimestampAsIs(queueDetails.assignedTime, 'datetime')}
        </Descriptions.Item>
      )}
      {queueDetails.lastRetryAt && (
        <Descriptions.Item label={t('trace.lastRetry')}>
          {formatTimestampAsIs(queueDetails.lastRetryAt, 'datetime')}
        </Descriptions.Item>
      )}
      <Descriptions.Item label={t('trace.totalDuration')}>
        {formatDurationFull(totalDurationSeconds)}
      </Descriptions.Item>
      {processingDurationSeconds > 0 && (
        <Descriptions.Item label={t('trace.processingDuration')}>
          {formatDurationFull(processingDurationSeconds)}
        </Descriptions.Item>
      )}
      <Descriptions.Item label={t('trace.createdBy')}>
        {normalizeToString(queueDetails, 'createdBy', 'CreatedBy') || '-'}
      </Descriptions.Item>
      <Descriptions.Item label={t('trace.retryCount')}>
        <Tag>{retryCount}/2</Tag>
      </Descriptions.Item>
      {lastFailureReason && (
        <Descriptions.Item label={t('trace.lastFailureReason')} span={2}>
          <Typography.Text type="warning">{lastFailureReason}</Typography.Text>
        </Descriptions.Item>
      )}
    </Descriptions>
  );
};
