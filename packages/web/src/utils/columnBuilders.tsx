/**
 * Column Definition Builder Utilities
 *
 * This module provides reusable column definition utilities for Ant Design tables
 * that standardize common patterns like status columns, priority columns, timestamps, etc.
 *
 * These utilities complement the existing column builders in @/components/common/columns
 * and provide higher-level abstractions for specific use cases like queue items.
 */

import React from 'react';
import { Space, Tag, Tooltip } from 'antd';
import { renderTimestampElement } from '@/components/common/columns';
import { RediaccButton, RediaccText } from '@/components/ui';
import { formatAge, PRIORITY_CONFIG } from '@/platform';
import type { QueueHealthStatus } from '@/platform';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  PlayCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import type { TooltipProps } from 'antd';
import type { ColumnType } from 'antd/es/table';

/**
 * Status configuration for column rendering
 */
export interface StatusConfig {
  color: string;
  label: string;
  icon?: React.ReactNode;
}

/**
 * Priority labels mapping
 */
export const DEFAULT_PRIORITY_LABELS: Record<number, string> = {
  1: 'Highest',
  2: 'High',
  3: 'Normal',
  4: 'Low',
  5: 'Lowest',
};

/**
 * Priority icons mapping
 */
export const PRIORITY_ICONS: Record<number, React.ReactNode | undefined> = {
  1: <ExclamationCircleOutlined />,
  2: undefined,
  3: undefined,
  4: undefined,
  5: undefined,
};

/**
 * Queue status icons mapping
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
 * Configuration for status column
 */
export interface StatusColumnConfig<T> {
  dataIndex: keyof T;
  title?: string;
  statusMap: Record<string, StatusConfig>;
  defaultConfig?: StatusConfig;
  width?: number;
  sorter?: boolean | ColumnType<T>['sorter'];
  tooltipFormatter?: (record: T) => string | undefined;
}

/**
 * Creates a status column with consistent styling and icon rendering
 *
 * @example
 * ```tsx
 * const statusColumn = createStatusColumn<QueueItem>({
 *   dataIndex: 'healthStatus',
 *   title: 'Status',
 *   statusMap: {
 *     PENDING: { color: 'blue', label: 'Pending', icon: <ClockCircleOutlined /> },
 *     COMPLETED: { color: 'green', label: 'Completed', icon: <CheckCircleOutlined /> },
 *   },
 * });
 * ```
 */
export function createStatusColumn<T>(config: StatusColumnConfig<T>): ColumnType<T> {
  const {
    dataIndex,
    title = 'Status',
    statusMap,
    defaultConfig = { color: 'default', label: 'Unknown' },
    width = 120,
    sorter,
    tooltipFormatter,
  } = config;

  const dataKey = String(dataIndex);

  let sorterFn: ColumnType<T>['sorter'] | undefined;
  if (sorter === true) {
    sorterFn = (a: T, b: T) => {
      const aValue = String((a as Record<string, unknown>)[dataKey] ?? '');
      const bValue = String((b as Record<string, unknown>)[dataKey] ?? '');
      return aValue.localeCompare(bValue);
    };
  } else if (typeof sorter === 'function') {
    sorterFn = sorter;
  }

  return {
    title,
    dataIndex: dataIndex as string,
    key: dataKey,
    width,
    align: 'center',
    sorter: sorterFn,
    render: (value: string, record: T) => {
      const status = String(value ?? '');
      const statusConfig = statusMap[status] || defaultConfig;
      const tooltipText = tooltipFormatter?.(record);

      return (
        <Tooltip title={tooltipText || statusConfig.label}>
          <Tag color={statusConfig.color} icon={statusConfig.icon}>
            {statusConfig.label}
          </Tag>
        </Tooltip>
      );
    },
  };
}

/**
 * Configuration for priority column
 */
export interface PriorityColumnConfig<T> {
  dataIndex: keyof T;
  title?: string;
  priorityLabels?: Record<number, string>;
  width?: number;
  sorter?: boolean;
  tooltipFormatter?: (priority: number, record: T) => React.ReactNode;
}

/**
 * Creates a priority column with tooltip and color coding
 *
 * @example
 * ```tsx
 * const priorityColumn = createPriorityColumn<QueueItem>({
 *   dataIndex: 'priority',
 *   title: 'Priority',
 *   tooltipFormatter: (priority) => `Priority level: ${priority}`,
 * });
 * ```
 */
export function createPriorityColumn<T>(config: PriorityColumnConfig<T>): ColumnType<T> {
  const {
    dataIndex,
    title = 'Priority',
    priorityLabels = DEFAULT_PRIORITY_LABELS,
    width = 140,
    sorter = true,
    tooltipFormatter,
  } = config;

  const dataKey = String(dataIndex);

  return {
    title,
    dataIndex: dataIndex as string,
    key: dataKey,
    width,
    sorter: sorter
      ? (a: T, b: T) => {
          const aPriority = Number((a as Record<string, unknown>)[dataKey] ?? 3);
          const bPriority = Number((b as Record<string, unknown>)[dataKey] ?? 3);
          return aPriority - bPriority;
        }
      : undefined,
    render: (value: number, record: T) => {
      const priority = value ?? 3;
      const label = priorityLabels[priority] || priorityLabels[3];
      const priorityConfig = PRIORITY_CONFIG[priority] || PRIORITY_CONFIG[3];
      const icon = PRIORITY_ICONS[priority];

      const tooltipContent = tooltipFormatter
        ? tooltipFormatter(priority, record)
        : `Priority: ${label}`;

      return (
        <Tooltip title={tooltipContent}>
          <Tag color={priorityConfig.color} icon={icon}>
            {label}
          </Tag>
        </Tooltip>
      );
    },
  };
}

/**
 * Configuration for timestamp column
 */
export interface TimestampColumnConfig<T> {
  dataIndex: keyof T;
  title: string;
  format?: 'relative' | 'absolute' | 'both';
  dateFormat?: string;
  width?: number;
  sorter?: boolean;
  defaultSortOrder?: ColumnType<T>['defaultSortOrder'];
}

/**
 * Creates a timestamp column with relative time display
 *
 * @example
 * ```tsx
 * const createdColumn = createTimestampColumn<QueueItem>({
 *   dataIndex: 'createdTime',
 *   title: 'Created',
 *   format: 'relative',
 * });
 * ```
 */
export function createTimestampColumn<T>(config: TimestampColumnConfig<T>): ColumnType<T> {
  const {
    dataIndex,
    title,
    format = 'absolute',
    dateFormat = 'YYYY-MM-DD HH:mm:ss',
    width = 180,
    sorter = true,
    defaultSortOrder,
  } = config;

  const dataKey = String(dataIndex);

  return {
    title,
    dataIndex: dataIndex as string,
    key: dataKey,
    width,
    sorter: sorter
      ? (a: T, b: T) => {
          const aValue = (a as Record<string, unknown>)[dataKey];
          const bValue = (b as Record<string, unknown>)[dataKey];
          const aTime = new Date(aValue as string | number | Date).getTime();
          const bTime = new Date(bValue as string | number | Date).getTime();
          return aTime - bTime;
        }
      : undefined,
    defaultSortOrder,
    render: (value: string | Date | null | undefined) => {
      if (!value) {
        return <RediaccText color="secondary">-</RediaccText>;
      }

      if (format === 'relative') {
        const now = new Date().getTime();
        const timestamp = new Date(value).getTime();
        const diffMinutes = Math.floor((now - timestamp) / (1000 * 60));
        return formatAge(diffMinutes);
      }

      if (format === 'both') {
        const now = new Date().getTime();
        const timestamp = new Date(value).getTime();
        const diffMinutes = Math.floor((now - timestamp) / (1000 * 60));
        const relativeTime = formatAge(diffMinutes);
        const absoluteTime = renderTimestampElement(value, dateFormat);

        return (
          <Tooltip title={absoluteTime}>
            <span>{relativeTime}</span>
          </Tooltip>
        );
      }

      return renderTimestampElement(value, dateFormat);
    },
  };
}

/**
 * Configuration for truncated column
 */
export interface TruncatedColumnConfig<T> {
  dataIndex: keyof T;
  title: string;
  maxWidth?: number;
  maxLength?: number;
  copyable?: boolean;
  code?: boolean;
  tooltipPlacement?: TooltipProps['placement'];
}

/**
 * Creates a truncated text column with tooltip
 *
 * @example
 * ```tsx
 * const taskIdColumn = createTruncatedColumn<QueueItem>({
 *   dataIndex: 'taskId',
 *   title: 'Task ID',
 *   maxLength: 8,
 *   copyable: true,
 *   code: true,
 * });
 * ```
 */
export function createTruncatedColumn<T>(config: TruncatedColumnConfig<T>): ColumnType<T> {
  const {
    dataIndex,
    title,
    maxWidth,
    maxLength = 20,
    copyable = false,
    code = false,
    tooltipPlacement = 'topLeft',
  } = config;

  const dataKey = String(dataIndex);

  return {
    title,
    dataIndex: dataIndex as string,
    key: dataKey,
    width: maxWidth,
    ellipsis: true,
    render: (value: string | null | undefined) => {
      if (!value) {
        return <RediaccText color="secondary">-</RediaccText>;
      }

      const shouldTruncate = value.length > maxLength;
      const displayText = shouldTruncate ? `${value.slice(0, maxLength)}...` : value;

      if (copyable || code) {
        return (
          <RediaccText code={code} copyable={copyable}>
            {displayText}
          </RediaccText>
        );
      }

      if (shouldTruncate) {
        return (
          <Tooltip title={value} placement={tooltipPlacement}>
            <span>{displayText}</span>
          </Tooltip>
        );
      }

      return <span>{value}</span>;
    },
  };
}

/**
 * Action item configuration
 */
export interface ActionItem<T> {
  key: string;
  label: string;
  icon?: React.ReactNode;
  onClick: (record: T) => void;
  danger?: boolean;
  disabled?: (record: T) => boolean;
  hidden?: (record: T) => boolean;
  loading?: boolean;
  tooltip?: string | ((record: T) => string);
}

/**
 * Configuration for actions column
 */
export interface ActionsColumnConfig<T> {
  actions: ActionItem<T>[];
  width?: number;
  title?: string;
}

/**
 * Creates an actions column with consistent styling
 *
 * @example
 * ```tsx
 * const actionsColumn = createActionsColumn<QueueItem>({
 *   actions: [
 *     {
 *       key: 'view',
 *       label: 'View',
 *       icon: <EyeOutlined />,
 *       onClick: handleView,
 *     },
 *     {
 *       key: 'delete',
 *       label: 'Delete',
 *       icon: <DeleteOutlined />,
 *       onClick: handleDelete,
 *       danger: true,
 *       hidden: (record) => record.status === 'COMPLETED',
 *     },
 *   ],
 * });
 * ```
 */
export function createActionsColumn<T>(config: ActionsColumnConfig<T>): ColumnType<T> {
  const { actions, width = 180, title = 'Actions' } = config;

  return {
    title,
    key: 'actions',
    width,
    render: (_: unknown, record: T) => {
      const visibleActions = actions.filter((action) => !action.hidden?.(record));

      if (visibleActions.length === 0) {
        return null;
      }

      return (
        <Space size="small">
          {visibleActions.map((action) => {
            const isDisabled = action.disabled?.(record) ?? false;
            const tooltipText =
              typeof action.tooltip === 'function' ? action.tooltip(record) : action.tooltip;

            return (
              <Tooltip key={action.key} title={tooltipText || action.label}>
                <RediaccButton
                  size="sm"
                  iconOnly
                  icon={action.icon}
                  onClick={() => action.onClick(record)}
                  danger={action.danger}
                  disabled={isDisabled}
                  loading={action.loading}
                  data-testid={`action-${action.key}-${(record as Record<string, unknown>).taskId || (record as Record<string, unknown>).id}`}
                  aria-label={action.label}
                />
              </Tooltip>
            );
          })}
        </Space>
      );
    },
  };
}

/**
 * Configuration for age column (minutes-based)
 */
export interface AgeColumnConfig<T> {
  dataIndex: keyof T;
  title?: string;
  width?: number;
  sorter?: boolean;
  colorize?: boolean;
  warningThreshold?: number; // minutes
  errorThreshold?: number; // minutes
}

/**
 * Creates an age column that displays time in human-readable format
 *
 * @example
 * ```tsx
 * const ageColumn = createAgeColumn<QueueItem>({
 *   dataIndex: 'ageInMinutes',
 *   title: 'Age',
 *   colorize: true,
 *   warningThreshold: 360, // 6 hours
 *   errorThreshold: 720, // 12 hours
 * });
 * ```
 */
export function createAgeColumn<T>(config: AgeColumnConfig<T>): ColumnType<T> {
  const {
    dataIndex,
    title = 'Age',
    width = 100,
    sorter = true,
    colorize = false,
    warningThreshold = 360,
    errorThreshold = 720,
  } = config;

  const dataKey = String(dataIndex);

  return {
    title,
    dataIndex: dataIndex as string,
    key: dataKey,
    width,
    sorter: sorter
      ? (a: T, b: T) => {
          const aValue = Number((a as Record<string, unknown>)[dataKey] ?? 0);
          const bValue = Number((b as Record<string, unknown>)[dataKey] ?? 0);
          return aValue - bValue;
        }
      : undefined,
    render: (minutes: number) => {
      const ageText = formatAge(minutes ?? 0);

      if (!colorize) {
        return ageText;
      }

      let color: string | undefined;
      if (minutes >= errorThreshold) {
        color = 'red';
      } else if (minutes >= warningThreshold) {
        color = 'orange';
      }

      return <RediaccText style={{ color }}>{ageText}</RediaccText>;
    },
  };
}

/**
 * Configuration for resource name column (machines, teams, bridges, etc.)
 */
export interface ResourceNameColumnConfig<T> {
  dataIndex: keyof T;
  title: string;
  icon?: React.ReactNode;
  width?: number;
  sorter?: boolean;
  strong?: boolean;
}

/**
 * Creates a resource name column with optional icon
 *
 * @example
 * ```tsx
 * const machineColumn = createResourceNameColumn<QueueItem>({
 *   dataIndex: 'machineName',
 *   title: 'Machine',
 *   icon: <DesktopOutlined />,
 * });
 * ```
 */
export function createResourceNameColumn<T>(config: ResourceNameColumnConfig<T>): ColumnType<T> {
  const { dataIndex, title, icon, width = 180, sorter = true, strong = false } = config;

  const dataKey = String(dataIndex);

  return {
    title,
    dataIndex: dataIndex as string,
    key: dataKey,
    width,
    sorter: sorter
      ? (a: T, b: T) => {
          const aValue = String((a as Record<string, unknown>)[dataKey] ?? '');
          const bValue = String((b as Record<string, unknown>)[dataKey] ?? '');
          return aValue.localeCompare(bValue);
        }
      : undefined,
    render: (name: string) => {
      if (!name) {
        return <RediaccText color="secondary">-</RediaccText>;
      }

      const content = strong ? <strong>{name}</strong> : name;

      if (icon) {
        return (
          <Space>
            {icon}
            {content}
          </Space>
        );
      }

      return content;
    },
  };
}
