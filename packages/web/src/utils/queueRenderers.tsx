/**
 * React rendering helpers for queue items
 * These use the shared core configurations but add React-specific rendering (icons, components)
 */

import React from 'react';
import { Tag, Tooltip } from 'antd';
import {
  formatAge,
  PRIORITY_CONFIG,
  QUEUE_STATUS_CONFIG,
  type QueueHealthStatus,
} from '@/platform';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  PlayCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';

/**
 * Status configuration with React icon components
 */
export const QUEUE_STATUS_ICONS: Record<QueueHealthStatus, React.ReactNode> = {
  PENDING: <ClockCircleOutlined />,
  ACTIVE: <PlayCircleOutlined />,
  STALE: <WarningOutlined />,
  STALE_PENDING: <WarningOutlined />,
  CANCELLING: <PlayCircleOutlined spin />,
  COMPLETED: <CheckCircleOutlined />,
  FAILED: <ExclamationCircleOutlined />,
  CANCELLED: <CloseCircleOutlined />,
  UNKNOWN: <ExclamationCircleOutlined />,
};

/**
 * Priority configuration with React icon components
 */
export const PRIORITY_ICONS: Record<number, React.ReactNode | undefined> = {
  1: <ExclamationCircleOutlined />,
  2: undefined,
  3: undefined,
  4: undefined,
  5: undefined,
};

/**
 * Render queue status tag with icon and tooltip
 */
export function renderQueueStatus(
  healthStatus: string,
  record: {
    status?: string | null;
    minutesSinceAssigned?: number | null;
    ageInMinutes?: number | null;
  }
): React.ReactElement {
  const config =
    QUEUE_STATUS_CONFIG[healthStatus as QueueHealthStatus] || QUEUE_STATUS_CONFIG.UNKNOWN;
  const icon = QUEUE_STATUS_ICONS[healthStatus as QueueHealthStatus] || QUEUE_STATUS_ICONS.UNKNOWN;

  // Show actual status alongside health status for active items
  const statusText =
    healthStatus === 'ACTIVE' && record.status
      ? `${record.status} (${healthStatus})`
      : healthStatus;

  // Generate tooltip text
  let tooltipText: string | undefined;
  if (record.minutesSinceAssigned) {
    tooltipText = `${record.minutesSinceAssigned} minutes since assigned`;
  } else if (healthStatus === 'STALE_PENDING') {
    const hoursOld = Math.floor((record.ageInMinutes || 0) / 60);
    tooltipText = `Pending for ${hoursOld} hours - may need attention`;
  }

  return (
    <Tooltip title={tooltipText}>
      <Tag color={config.color} icon={icon}>
        {statusText}
      </Tag>
    </Tooltip>
  );
}

/**
 * Render priority tag with icon and tooltip
 */
export function renderPriority(
  priorityLabel: string | undefined | null,
  priority: number | undefined | null,
  tooltipContent: React.ReactNode
): React.ReactElement | null {
  if (!priorityLabel || !priority) {
    return null;
  }

  const config = PRIORITY_CONFIG[priority] || PRIORITY_CONFIG[3];
  const icon = PRIORITY_ICONS[priority];

  return (
    <Tooltip title={tooltipContent}>
      <Tag color={config.color} icon={icon}>
        {priorityLabel}
      </Tag>
    </Tooltip>
  );
}

/**
 * Render age in human-readable format
 * Uses the shared formatAge function from core
 */
export function renderAge(minutes: number): string {
  return formatAge(minutes);
}
