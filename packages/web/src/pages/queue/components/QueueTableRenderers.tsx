import React from 'react';
import { Flex, Tag, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  formatTimestampAsIs,
  getSeverityColor,
  parseFailureReason,
  STALE_TASK_CONSTANTS,
} from '@/platform';
import { ExclamationCircleOutlined } from '@/utils/optimizedIcons';
import { renderPriority } from '@/utils/queueRenderers';
import type { ParsedError } from '@rediacc/shared/error-parser';
import type { GetTeamQueueItems_ResultSet1 as QueueItem } from '@rediacc/shared/types';

interface PriorityWithTooltipProps {
  priorityLabel: string | undefined;
  record: QueueItem;
}

export const PriorityWithTooltip: React.FC<PriorityWithTooltipProps> = ({
  priorityLabel,
  record,
}) => {
  const { t } = useTranslation(['queue']);

  const tooltipContent = (
    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 200 }}>
      <Typography.Text style={{ display: 'block', fontWeight: 700 }}>
        {priorityLabel}
      </Typography.Text>
      <Typography.Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
        {record.priority === 1 ? t('queue:priorityTooltipP1') : t('queue:priorityTooltipTier')}
      </Typography.Text>
    </div>
  );

  return (
    renderPriority(priorityLabel, record.priority, tooltipContent) || (
      <Typography.Text type="secondary">-</Typography.Text>
    )
  );
};

interface AgeRendererProps {
  ageInMinutes: number;
  record: QueueItem;
}

export const AgeRenderer: React.FC<AgeRendererProps> = ({ ageInMinutes, record }) => {
  const hours = Math.floor(ageInMinutes / 60);
  const minutes = ageInMinutes % 60;

  let ageText = '';
  if (hours > 0) {
    ageText = `${hours}h ${minutes}m`;
  } else {
    ageText = `${minutes}m`;
  }

  // Color coding based on age and status
  let color: string | undefined;
  if (record.status === 'PENDING' && hours >= 12) {
    color = 'red';
  } else if (record.status === 'PENDING' && hours >= 6) {
    color = 'orange';
  }

  return <Typography.Text style={{ color }}>{ageText}</Typography.Text>;
};

interface ErrorRetriesRendererProps {
  retryCount: number | undefined;
  record: QueueItem;
}

export const ErrorRetriesRenderer: React.FC<ErrorRetriesRendererProps> = ({
  retryCount,
  record,
}) => {
  if (!retryCount && retryCount !== 0) {
    return (
      <Typography.Text type="secondary" style={{ color: 'var(--ant-color-text-secondary)' }}>
        -
      </Typography.Text>
    );
  }

  const maxRetries = STALE_TASK_CONSTANTS.MAX_RETRY_COUNT;
  let retryColor: string;
  if (retryCount === 0) {
    retryColor = 'green';
  } else if (retryCount < maxRetries - 1) {
    retryColor = 'orange';
  } else {
    retryColor = 'red';
  }
  const icon =
    retryCount >= maxRetries - 1 && record.permanentlyFailed ? (
      <ExclamationCircleOutlined />
    ) : undefined;

  // Parse error messages using consolidated utility function
  const { allErrors, primaryError } = parseFailureReason(record.lastFailureReason);

  return (
    <Flex vertical gap={4} style={{ width: '100%' }}>
      {/* Error messages with severity badges */}
      {allErrors.length > 0 && (
        <Tooltip
          title={
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 200 }}>
              {allErrors.map((error: ParsedError, index: number) => (
                <Typography.Text
                  key={`${error.message}-${index}`}
                  style={{ display: 'block', fontSize: 14 }}
                >
                  {error.severity && <strong>[{error.severity}]</strong>} {error.message}
                </Typography.Text>
              ))}
              {record.lastRetryAt && (
                <Typography.Text style={{ display: 'block', fontSize: 14 }}>
                  Last retry: {formatTimestampAsIs(record.lastRetryAt, 'datetime')}
                </Typography.Text>
              )}
            </div>
          }
        >
          <div style={{ width: '100%' }}>
            {/* Show primary (highest severity) error */}
            <Flex gap={4} style={{ width: '100%' }}>
              {primaryError?.severity && (
                <Tag
                  color={getSeverityColor(primaryError.severity)}
                  style={{ fontSize: 12, lineHeight: 1.2 }}
                >
                  {primaryError.severity}
                </Tag>
              )}
              <Typography.Text
                style={{
                  display: 'inline-flex',
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  fontSize: 14,
                  color: 'var(--ant-color-text-tertiary)',
                }}
              >
                {primaryError?.message}
              </Typography.Text>
            </Flex>
            {/* Show count of additional errors if any */}
            {allErrors.length > 1 && (
              <Typography.Text
                style={{
                  fontStyle: 'italic',
                  fontSize: 12,
                  color: 'var(--ant-color-text-tertiary)',
                }}
              >
                +{allErrors.length - 1} more {allErrors.length - 1 === 1 ? 'message' : 'messages'}
              </Typography.Text>
            )}
          </div>
        </Tooltip>
      )}

      {/* Retry count badge */}
      <Tag color={retryColor} icon={icon}>
        {retryCount}/{maxRetries} retries
      </Tag>
    </Flex>
  );
};
