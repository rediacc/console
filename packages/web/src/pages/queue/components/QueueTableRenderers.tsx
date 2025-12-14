import React from 'react';
import { useTranslation } from 'react-i18next';
import { RediaccStack, RediaccText, RediaccTooltip } from '@/components/ui';
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
import {
  AdditionalMessagesText,
  AgeText,
  ErrorMessageText,
  LastRetryText,
  PriorityTooltipTitle,
  RetrySummaryTag,
  SeverityPill,
  TooltipContent,
  TooltipContentSection,
  TruncatedErrorText,
} from '../styles';

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
    <TooltipContent>
      <PriorityTooltipTitle>{priorityLabel}</PriorityTooltipTitle>
      <RediaccText variant="caption" as="div">
        {record.priority === 1 ? t('queue:priorityTooltipP1') : t('queue:priorityTooltipTier')}
      </RediaccText>
    </TooltipContent>
  );

  return (
    renderPriority(priorityLabel, record.priority, tooltipContent) || (
      <RediaccText color="secondary">-</RediaccText>
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

  return <AgeText $color={color}>{ageText}</AgeText>;
};

interface ErrorRetriesRendererProps {
  retryCount: number | undefined;
  record: QueueItem;
}

export const ErrorRetriesRenderer: React.FC<ErrorRetriesRendererProps> = ({
  retryCount,
  record,
}) => {
  if (!retryCount && retryCount !== 0) return <RediaccText color="secondary">-</RediaccText>;

  const maxRetries = STALE_TASK_CONSTANTS.MAX_RETRY_COUNT;
  const retryColor = retryCount === 0 ? 'green' : retryCount < maxRetries - 1 ? 'orange' : 'red';
  const icon =
    retryCount >= maxRetries - 1 && record.permanentlyFailed ? (
      <ExclamationCircleOutlined />
    ) : undefined;

  // Parse error messages using consolidated utility function
  const { allErrors, primaryError } = parseFailureReason(record.lastFailureReason);

  return (
    <RediaccStack variant="column" fullWidth gap="xs">
      {/* Error messages with severity badges */}
      {allErrors.length > 0 && (
        <RediaccTooltip
          title={
            <TooltipContent>
              {allErrors.map((error: ParsedError, index: number) => (
                <ErrorMessageText
                  key={`${error.message}-${index}`}
                  $isLast={index === allErrors.length - 1}
                >
                  {error.severity && <strong>[{error.severity}]</strong>} {error.message}
                </ErrorMessageText>
              ))}
              {record.lastRetryAt && (
                <LastRetryText>
                  Last retry: {formatTimestampAsIs(record.lastRetryAt, 'datetime')}
                </LastRetryText>
              )}
            </TooltipContent>
          }
        >
          <TooltipContentSection>
            {/* Show primary (highest severity) error */}
            <RediaccStack direction="horizontal" gap={4} style={{ width: '100%', marginBottom: 2 }}>
              {primaryError?.severity && (
                <SeverityPill $color={getSeverityColor(primaryError.severity)}>
                  {primaryError.severity}
                </SeverityPill>
              )}
              <TruncatedErrorText as="span">{primaryError?.message}</TruncatedErrorText>
            </RediaccStack>
            {/* Show count of additional errors if any */}
            {allErrors.length > 1 && (
              <AdditionalMessagesText>
                +{allErrors.length - 1} more {allErrors.length - 1 === 1 ? 'message' : 'messages'}
              </AdditionalMessagesText>
            )}
          </TooltipContentSection>
        </RediaccTooltip>
      )}

      {/* Retry count badge */}
      <RetrySummaryTag $color={retryColor} icon={icon}>
        {retryCount}/{maxRetries} retries
      </RetrySummaryTag>
    </RediaccStack>
  );
};
