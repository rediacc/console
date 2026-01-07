import React from 'react';
import { Space, Timeline, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { formatTimestampAsIs, normalizeToString } from '@/platform';
import type { QueueTraceLog } from '@rediacc/shared/types';
import type { TimelineViewProps } from '../types';

export const TimelineView: React.FC<TimelineViewProps> = ({ traceLogs }) => {
  const { t } = useTranslation('queue');
  return (
    <Timeline
      mode="left"
      className="queue-trace-timeline"
      data-testid="queue-trace-timeline"
      items={traceLogs.map((log: QueueTraceLog) => {
        const action = normalizeToString(log, 'action', 'Action');
        const timestamp = normalizeToString(log, 'timestamp', 'Timestamp');
        const details = normalizeToString(log, 'details', 'Details');
        const actionByUser = normalizeToString(log, 'actionByUser', 'ActionByUser');

        // Determine timeline item color based on action type
        // Using grayscale system - only 'red' for actual errors
        let color = 'gray';
        if (action === 'QUEUE_ITEM_CANCELLED') color = 'red';
        else if (action === 'QUEUE_ITEM_FAILED') color = 'red';
        else if (action.includes('ERROR') || action.includes('FAILED')) color = 'red';

        return {
          color,
          children: (
            <Space direction="vertical" size={0}>
              <Typography.Text strong>
                {action.replace('QUEUE_ITEM_', '').replace(/_/g, ' ')}
              </Typography.Text>
              <Typography.Text>{formatTimestampAsIs(timestamp, 'datetime')}</Typography.Text>
              {details && <Typography.Text>{details}</Typography.Text>}
              {actionByUser && (
                <Typography.Text>
                  {t('trace.actionBy')}: {actionByUser}
                </Typography.Text>
              )}
            </Space>
          ),
        };
      })}
    />
  );
};
