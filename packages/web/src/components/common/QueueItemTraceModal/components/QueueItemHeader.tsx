import React from 'react';
import { Card, Flex, Progress, Space, Steps, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('queue');
  const simplifiedStatus = getSimplifiedStatus(queueDetails);
  const status = normalizeToString(queueDetails, 'status', 'Status');

  return (
    <Card data-testid="queue-trace-simple-overview">
      <Flex vertical className="w-full">
        {/* Status Summary */}
        <Flex className="text-center" justify="center">
          <Space size="large">
            <Typography.Text
              className={`queue-trace-status-icon ${simplifiedStatus.status === 'Processing' ? 'processing' : ''}`}
            >
              {simplifiedStatus.icon}
            </Typography.Text>
            <Typography.Title level={3}>
              {t('trace.taskStatus', { status: simplifiedStatus.status })}
            </Typography.Title>
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
              title: t('trace.assignedStep'),
              description: queueDetails.assignedTime
                ? formatTimestampAsIs(queueDetails.assignedTime, 'time')
                : t('trace.waiting'),
            },
            {
              title: t('trace.processingStep'),
              description: (() => {
                const currentStep = getCurrentStep(queueDetails);
                const processingTimestamp = getTimelineTimestamp(
                  traceLogs,
                  'QUEUE_ITEM_PROCESSING',
                  'QUEUE_ITEM_RESPONSE_UPDATED'
                );

                if (status === 'PROCESSING') {
                  return processingTimestamp ?? t('trace.inProgress');
                }

                if (status === 'CANCELLING') {
                  return t('trace.cancelling');
                }

                if (currentStep >= 1) {
                  return processingTimestamp ?? t('trace.processed');
                }

                return '';
              })(),
            },
            {
              title: t('trace.completedStep'),
              description: (() => {
                if (status === 'COMPLETED') {
                  const timestamp = getTimelineTimestamp(traceLogs, 'QUEUE_ITEM_COMPLETED');
                  return `${t('trace.done')}${timestamp ? ` - ${timestamp}` : ''}`;
                }
                if (status === 'FAILED') {
                  const timestamp = getTimelineTimestamp(traceLogs, 'QUEUE_ITEM_FAILED');
                  return `${t('trace.failed')}${timestamp ? ` - ${timestamp}` : ''}`;
                }
                if (status === 'CANCELLED') {
                  const timestamp = getTimelineTimestamp(traceLogs, 'QUEUE_ITEM_CANCELLED');
                  return `${t('trace.cancelled')}${timestamp ? ` - ${timestamp}` : ''}`;
                }
                if (status === 'CANCELLING') {
                  return t('trace.cancelling');
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
              <Typography.Text className="italic text-center text-xs">
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
            status={(() => {
              if (simplifiedStatus.status === 'Failed' || simplifiedStatus.status === 'Cancelled') {
                return 'exception';
              } else if (simplifiedStatus.status === 'Completed') {
                return 'success';
              }
              return 'active';
            })()}
          />
        )}
      </Flex>
    </Card>
  );
};
