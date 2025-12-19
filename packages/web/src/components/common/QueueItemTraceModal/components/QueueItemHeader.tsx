import React from 'react';
import { Progress, Space, Steps, Typography } from 'antd';
import { RediaccStack } from '@/components/ui';
import { normalizeToString, formatTimestampAsIs } from '@/platform';
import { SpacedCardBottom, NoteWrapper, ItalicCaption } from '../styles';
import { getCurrentStep, getSimplifiedStatus, getTimelineTimestamp } from '../utils';
import type { TraceLog } from '../types';

interface QueueItemHeaderProps {
  queueDetails: Record<string, unknown>;
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
    <SpacedCardBottom data-testid="queue-trace-simple-overview">
      <RediaccStack variant="spaced-column" fullWidth>
        {/* Status Summary */}
        <div style={{ textAlign: 'center' }}>
          <Space size="large">
            <span
              className={`queue-trace-status-icon ${simplifiedStatus.status === 'Processing' ? 'processing' : ''}`}
            >
              {simplifiedStatus.icon}
            </span>
            <Typography.Title level={3}>Task {simplifiedStatus.status}</Typography.Title>
          </Space>
        </div>

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
                ? formatTimestampAsIs(queueDetails.assignedTime, 'time')
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
            <NoteWrapper>
              <ItalicCaption>{progressMessage}</ItalicCaption>
            </NoteWrapper>
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
      </RediaccStack>
    </SpacedCardBottom>
  );
};
