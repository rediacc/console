import React from 'react';
import dayjs from 'dayjs';
import styled from 'styled-components';
import { RediaccTag, RediaccText, RediaccTooltip } from '@/components/ui';

/**
 * Styled version tag used across column renderers
 */
export const VersionTag = styled(RediaccTag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border-color: ${({ theme }) => theme.colors.info};
    color: ${({ theme }) => theme.colors.info};
    background: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

/**
 * Styled truncated text for monospace display
 */
const TruncatedMonoText = styled.span`
  font-family: ${({ theme }) => theme.fontFamily.MONO};
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: var(--color-text-secondary);
`;

/**
 * Styled status icon wrapper
 */
const StatusIconWrapper = styled.span`
  font-size: ${({ theme }) => theme.spacing.MD}px;
  cursor: pointer;
`;

/**
 * Render a timestamp in a consistent format
 * @param timestamp - ISO timestamp string or Date object
 * @param format - Optional format string (defaults to 'YYYY-MM-DD HH:mm:ss')
 * @returns Formatted timestamp string
 */
export const renderTimestamp = (
  timestamp: string | Date | null | undefined,
  format: string = 'YYYY-MM-DD HH:mm:ss'
): string => {
  if (!timestamp) {
    return '-';
  }
  return dayjs(timestamp).format(format);
};

/**
 * Render a timestamp column element
 * @param timestamp - ISO timestamp string or Date object
 * @param format - Optional format string (defaults to 'YYYY-MM-DD HH:mm:ss')
 * @returns React element with formatted timestamp
 */
export const renderTimestampElement = (
  timestamp: string | Date | null | undefined,
  format: string = 'YYYY-MM-DD HH:mm:ss'
): React.ReactNode => {
  if (!timestamp) {
    return <RediaccText color="secondary">-</RediaccText>;
  }
  return dayjs(timestamp).format(format);
};

/**
 * Render a truncated ID/GUID with tooltip showing full value
 * @param id - The full ID string
 * @param length - Number of characters to show (default 8)
 * @param showEllipsis - Whether to show "..." after truncated text
 * @returns React element with truncated ID and tooltip
 */
export const renderTruncatedId = (
  id: string | null | undefined,
  length: number = 8,
  showEllipsis: boolean = true
): React.ReactNode => {
  if (!id) {
    return <RediaccText color="secondary">-</RediaccText>;
  }

  const truncated = id.substring(0, length);
  const display = showEllipsis ? `${truncated}...` : truncated;

  return (
    <RediaccTooltip title={id}>
      <TruncatedMonoText>{display}</TruncatedMonoText>
    </RediaccTooltip>
  );
};

/**
 * Render a copyable ID/GUID with tooltip
 * @param id - The full ID string
 * @param length - Number of characters to show (default 8)
 * @returns React element with copyable truncated ID
 */
export const renderCopyableId = (
  id: string | null | undefined,
  length: number = 8
): React.ReactNode => {
  if (!id) {
    return <RediaccText color="secondary">-</RediaccText>;
  }

  return (
    <RediaccText code copyable>
      {id.substring(0, length)}...
    </RediaccText>
  );
};

/**
 * Render a version number in a consistent tag format
 * @param version - Version number
 * @param formatFn - Optional function to format the version (e.g., for i18n)
 * @returns React element with version tag
 */
export const renderVersionTag = (
  version: number | null | undefined,
  formatFn?: (version: number) => string
): React.ReactNode => {
  if (version === null || version === undefined) {
    return <RediaccText color="secondary">-</RediaccText>;
  }

  const label = formatFn ? formatFn(version) : `v${version}`;
  return <VersionTag>{label}</VersionTag>;
};

/**
 * Status color configuration type
 */
export interface StatusConfig {
  color: string;
  icon?: React.ReactNode;
  label?: string;
}

/**
 * Create a status renderer with icon and tooltip
 * @param statusMap - Map of status values to their configuration
 * @param defaultConfig - Default configuration for unknown statuses
 * @returns Render function for status icons with tooltips
 */
export const createStatusRenderer = <T extends string>(
  statusMap: Record<T, StatusConfig>,
  defaultConfig: StatusConfig = { color: 'default' }
) => {
  function StatusRenderer(status: T): React.ReactNode {
    const config = statusMap[status] || defaultConfig;
    return (
      <RediaccTooltip title={config.label || status}>
        <StatusIconWrapper>{config.icon}</StatusIconWrapper>
      </RediaccTooltip>
    );
  }

  return StatusRenderer;
};

/**
 * Render age/duration in a human-readable format
 * @param minutes - Number of minutes
 * @returns Formatted string like "5m", "2h 30m", "1d 5h"
 */
export const renderAge = (minutes: number | null | undefined): string => {
  if (minutes === null || minutes === undefined) {
    return '-';
  }

  if (minutes < 60) {
    return `${minutes}m`;
  }
  if (minutes < 1440) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }

  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
};

/**
 * Render a boolean value as Yes/No text
 * @param value - Boolean value
 * @param yesText - Text for true value (default 'Yes')
 * @param noText - Text for false value (default 'No')
 * @returns React element
 */
export const renderBoolean = (
  value: boolean | null | undefined,
  yesText: string = 'Yes',
  noText: string = 'No'
): React.ReactNode => {
  if (value === null || value === undefined) {
    return <RediaccText color="secondary">-</RediaccText>;
  }
  return value ? (
    <RediaccTag variant="success">{yesText}</RediaccTag>
  ) : (
    <RediaccTag>{noText}</RediaccTag>
  );
};
