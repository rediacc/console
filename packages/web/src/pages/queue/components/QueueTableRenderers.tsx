import React from 'react';
import { Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useTheme as useStyledTheme } from 'styled-components';
import { RediaccStack, RediaccText } from '@/components/ui';
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
  TooltipContent,
  TooltipContentSection,
  TooltipPrimaryRow,
  SeverityPill,
  TruncatedErrorText,
  RetrySummaryTag,
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
  const theme = useStyledTheme();

  const tooltipContent = (
    <TooltipContent>
      <RediaccText
        weight="bold"
        style={{ margin: 0, display: 'block', marginBottom: theme.spacing.XS / 2 }}
      >
        {priorityLabel}
      </RediaccText>
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
  const theme = useStyledTheme();
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

  return <RediaccText style={{ color: color || theme.colors.textPrimary }}>{ageText}</RediaccText>;
};

interface ErrorRetriesRendererProps {
  retryCount: number | undefined;
  record: QueueItem;
}

export const ErrorRetriesRenderer: React.FC<ErrorRetriesRendererProps> = ({
  retryCount,
  record,
}) => {
  const theme = useStyledTheme();

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
        <Tooltip
          title={
            <TooltipContent>
              {allErrors.map((error: ParsedError, index: number) => (
                <RediaccText
                  key={`${error.message}-${index}`}
                  size="sm"
                  style={{
                    display: 'block',
                    marginBottom: index === allErrors.length - 1 ? 0 : theme.spacing.XS / 2,
                  }}
                >
                  {error.severity && <strong>[{error.severity}]</strong>} {error.message}
                </RediaccText>
              ))}
              {record.lastRetryAt && (
                <RediaccText
                  size="sm"
                  style={{
                    display: 'block',
                    marginTop: theme.spacing.XS,
                    paddingTop: theme.spacing.XS / 2,
                    borderTop: `1px solid ${theme.colors.borderSecondary}`,
                  }}
                >
                  Last retry: {formatTimestampAsIs(record.lastRetryAt, 'datetime')}
                </RediaccText>
              )}
            </TooltipContent>
          }
        >
          <TooltipContentSection>
            {/* Show primary (highest severity) error */}
            <TooltipPrimaryRow>
              {primaryError?.severity && (
                <SeverityPill $color={getSeverityColor(primaryError.severity)}>
                  {primaryError.severity}
                </SeverityPill>
              )}
              <TruncatedErrorText as="span">{primaryError?.message}</TruncatedErrorText>
            </TooltipPrimaryRow>
            {/* Show count of additional errors if any */}
            {allErrors.length > 1 && (
              <RediaccText size="xs" color="muted" style={{ fontStyle: 'italic' }}>
                +{allErrors.length - 1} more {allErrors.length - 1 === 1 ? 'message' : 'messages'}
              </RediaccText>
            )}
          </TooltipContentSection>
        </Tooltip>
      )}

      {/* Retry count badge */}
      <RetrySummaryTag $color={retryColor} icon={icon}>
        {retryCount}/{maxRetries} retries
      </RetrySummaryTag>
    </RediaccStack>
  );
};
