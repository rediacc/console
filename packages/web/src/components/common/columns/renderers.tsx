import { Tag, Tooltip, Typography } from 'antd';
import dayjs from 'dayjs';
import React from 'react';

/**
 * Styled status icon wrapper
 */
const statusIconWrapperStyle: React.CSSProperties = {
  fontSize: 16,
  cursor: 'pointer',
};

/**
 * Render a timestamp in a consistent format
 * @param timestamp - ISO timestamp string or Date object
 * @param format - Optional format string (defaults to 'YYYY-MM-DD HH:mm:ss')
 * @returns Formatted timestamp string
 */
export const renderTimestamp = (
  timestamp: string | Date | null | undefined,
  format = 'YYYY-MM-DD HH:mm:ss'
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
  format = 'YYYY-MM-DD HH:mm:ss'
): React.ReactNode => {
  if (!timestamp) {
    return <Typography.Text>-</Typography.Text>;
  }
  return dayjs(timestamp).format(format);
};

/**
 * Status configuration type
 */
export interface StatusConfig {
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
  _defaultConfig: StatusConfig = {}
) => {
  function StatusRenderer(status: T): React.ReactNode {
    const config = statusMap[status];
    return (
      <Tooltip title={config.label ?? status}>
        {/* eslint-disable-next-line no-restricted-syntax */}
        <Typography.Text style={statusIconWrapperStyle}>{config.icon}</Typography.Text>
      </Tooltip>
    );
  }

  return StatusRenderer;
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
  yesText = 'Yes',
  noText = 'No'
): React.ReactNode => {
  if (value === null || value === undefined) {
    return <Typography.Text>-</Typography.Text>;
  }
  return value ? <Tag>{yesText}</Tag> : <Tag>{noText}</Tag>;
};
