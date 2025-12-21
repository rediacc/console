import React from 'react';
import { Card, Flex, Progress, Space, Steps, Typography } from 'antd';
import { normalizeToString, formatTimestampAsIs } from '@/platform';
import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import { getCurrentStep, getSimplifiedStatus, getTimelineTimestamp } from '../utils';
import type { TraceLog } from '../types';

interface QueueItemHeaderProps {
  queueDetails: GetTeamQueueItems_ResultSet1;
  traceLogs: TraceLog[];
  progressMessage: string | null;
  consoleProgress: number | null;
}

export const QueueItemHeader: React.FC<QueueItemHeaderProps> = ({
  queueDetails,
  traceLogs,
  progressMessage,
  consoleProgress,
}) => {
  const simplifiedStatus = getSimplifiedStatus(queueDetails);
  const status = normalizeToString(queueDetails, 'status', 'Status');

  return (
    <Card data-testid="queue-trace-simple-overview">
      <Flex vertical gap={24} style={{ width: '100%' }}>
        {/* Status Summary */}
        <Flex style={{ textAlign: 'center' }} justify="center">
          <Space size="large">
            <Typography.Text
              className={`queue-trace-status-icon ${simplifiedStatus.status === 'Processing' ? 'processing' : ''}`}
            >
              {simplifiedStatus.icon}
            </Typography.Text>
            <Typography.Title level={3}>Task {simplifiedStatus.status}</Typography.Title>
          </Space>
        </Flex>

        {/* Steps */}
        <Steps
          data-testid="queue-trace-steps"
          className="queue-trace-steps"
          current={getCurrentStep(queueDetails)}
          status={getCurrentStep(queueDetails) === -1 ? 'error' : undefined}
          size="small"
          items={[
            {
              title: 'Assigned',
              description: queueDetails.assignedTime
                ? formatTimestampAsIs(queueDetails.assignedTime as string, 'time')
                : 'Waiting',
            },
            {
              title: 'Processing',
              description: (() => {
                const currentStep = getCurrentStep(queueDetails);
                const processingTimestamp = getTimelineTimestamp(
                  traceLogs,
                  'QUEUE_ITEM_PROCESSING',
                  'QUEUE_ITEM_RESPONSE_UPDATED'
                );

                if (status === 'PROCESSING') {
                  return processingTimestamp || 'In Progress';
                }

                if (status === 'CANCELLING') {
                  return 'Cancelling...';
                }

                if (currentStep >= 1) {
                  return processingTimestamp || 'Processed';
                }

                return '';
              })(),
            },
            {
              title: 'Completed',
              description: (() => {
                if (status === 'COMPLETED') {
                  const timestamp = getTimelineTimestamp(traceLogs, 'QUEUE_ITEM_COMPLETED');
                  return `Done${timestamp ? ' - ' + timestamp : ''}`;
                }
                if (status === 'FAILED') {
                  const timestamp = getTimelineTimestamp(traceLogs, 'QUEUE_ITEM_FAILED');
                  return `Failed${timestamp ? ' - ' + timestamp : ''}`;
                }
                if (status === 'CANCELLED') {
                  const timestamp = getTimelineTimestamp(traceLogs, 'QUEUE_ITEM_CANCELLED');
                  return `Cancelled${timestamp ? ' - ' + timestamp : ''}`;
                }
                if (status === 'CANCELLING') {
                  return 'Cancelling';
                }
                return '';
              })(),
            },
          ]}
        />

        {/* Progress Message */}
        {progressMessage &&
          status !== 'COMPLETED' &&
          status !== 'FAILED' &&
          status !== 'CANCELLED' && (
            <Flex justify="center">
              <Typography.Text
                type="secondary"
                style={{ fontStyle: 'italic', textAlign: 'center', fontSize: 12 }}
              >
                {progressMessage}
              </Typography.Text>
            </Flex>
          )}

        {/* Progress Bar */}
        {consoleProgress !== null && (
          <Progress
            data-testid="queue-trace-progress"
            className="queue-trace-progress"
            percent={consoleProgress}
            status={
              simplifiedStatus.status === 'Failed' || simplifiedStatus.status === 'Cancelled'
                ? 'exception'
                : simplifiedStatus.status === 'Completed'
                  ? 'success'
                  : 'active'
            }
          />
        )}
      </Flex>
    </Card>
  );
};
