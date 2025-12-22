import React from 'react';
import { Flex, Tag, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { formatTimestampAsIs, parseFailureReason, STALE_TASK_CONSTANTS } from '@/platform';
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
    <Flex vertical>
      <Typography.Text className="block">{priorityLabel}</Typography.Text>
      <Typography.Text className="block">
        {record.priority === 1 ? t('queue:priorityTooltipP1') : t('queue:priorityTooltipTier')}
      </Typography.Text>
    </Flex>
  );

  return (
    renderPriority(priorityLabel, record.priority, tooltipContent) || (
      <Typography.Text>-</Typography.Text>
    )
  );
};

interface AgeRendererProps {
  ageInMinutes: number;
  record: QueueItem;
}

export const AgeRenderer: React.FC<AgeRendererProps> = ({ ageInMinutes, record: _record }) => {
  const hours = Math.floor(ageInMinutes / 60);
  const minutes = ageInMinutes % 60;

  let ageText = '';
  if (hours > 0) {
    ageText = `${hours}h ${minutes}m`;
  } else {
    ageText = `${minutes}m`;
  }

  return <Typography.Text>{ageText}</Typography.Text>;
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
    return <Typography.Text>-</Typography.Text>;
  }

  const icon =
    retryCount >= STALE_TASK_CONSTANTS.MAX_RETRY_COUNT - 1 && record.permanentlyFailed ? (
      <ExclamationCircleOutlined />
    ) : undefined;

  // Parse error messages using consolidated utility function
  const { allErrors, primaryError } = parseFailureReason(record.lastFailureReason);

  return (
    <Flex vertical gap={4} className="w-full">
      {/* Error messages with severity badges */}
      {allErrors.length > 0 && (
        <Tooltip
          title={
            <Flex vertical>
              {allErrors.map((error: ParsedError, index: number) => (
                <Typography.Text key={`${error.message}-${index}`} className="block">
                  {error.severity && <strong>[{error.severity}]</strong>} {error.message}
                </Typography.Text>
              ))}
              {record.lastRetryAt && (
                <Typography.Text className="block">
                  Last retry: {formatTimestampAsIs(record.lastRetryAt, 'datetime')}
                </Typography.Text>
              )}
            </Flex>
          }
        >
          <Flex vertical className="w-full">
            {/* Show primary (highest severity) error */}
            <Flex gap={4} className="w-full">
              {primaryError?.severity && <Tag>{primaryError.severity}</Tag>}
              <Typography.Text className="inline-flex flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
                {primaryError?.message}
              </Typography.Text>
            </Flex>
            {/* Show count of additional errors if any */}
            {allErrors.length > 1 && (
              <Typography.Text>
                +{allErrors.length - 1} more {allErrors.length - 1 === 1 ? 'message' : 'messages'}
              </Typography.Text>
            )}
          </Flex>
        </Tooltip>
      )}

      {/* Retry count badge */}
      <Tag icon={icon}>
        {retryCount}/{STALE_TASK_CONSTANTS.MAX_RETRY_COUNT} retries
      </Tag>
    </Flex>
  );
};
