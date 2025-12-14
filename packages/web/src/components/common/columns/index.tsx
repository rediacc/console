import React from 'react';
import { DeleteOutlined, EditOutlined, EyeOutlined, MoreOutlined } from '@ant-design/icons';
import { Space } from 'antd';
import { RediaccButton, RediaccDropdown, RediaccText, RediaccTooltip } from '@/components/ui';
import i18n from '@/i18n/config';
import {
  createStatusRenderer,
  renderTimestampElement,
  type StatusConfig,
  VersionTag,
} from './renderers';
import type { MenuProps, TooltipProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';

/**
 * Shared table column definitions to ensure consistency across pages
 * Import specific columns or use the factories to create customized versions
 */

// Type for column factory functions
type ColumnFactory<T> = (options?: {
  title?: string;
  sorter?: boolean;
  filterable?: boolean;
  render?: (value: string, record: T) => React.ReactNode;
}) => ColumnsType<T>[number];

type ColumnDataIndex<T> = Extract<keyof T, string | number> | string;

/**
 * Team name column - used across machines, credentials, storage, etc.
 */
export const teamNameColumn = <T extends { teamName?: string }>(
  options: Parameters<ColumnFactory<T>>[0] = {}
): ColumnsType<T>[number] => ({
  title: options.title || 'Team',
  dataIndex: 'teamName',
  key: 'teamName',
  width: 150,
  sorter:
    options.sorter !== false
      ? (a, b) => (a.teamName || '').localeCompare(b.teamName || '')
      : undefined,
  render: options.render,
});

/**
 * Bridge name column
 */
export const bridgeNameColumn = <T extends { bridgeName?: string }>(
  options: Parameters<ColumnFactory<T>>[0] = {}
): ColumnsType<T>[number] => ({
  title: options.title || 'Bridge',
  dataIndex: 'bridgeName',
  key: 'bridgeName',
  width: 150,
  sorter:
    options.sorter !== false
      ? (a, b) => (a.bridgeName || '').localeCompare(b.bridgeName || '')
      : undefined,
  render: options.render,
});

/**
 * Machine name column
 */
export const machineNameColumn = <T extends { machineName?: string }>(
  options: Parameters<ColumnFactory<T>>[0] = {}
): ColumnsType<T>[number] => ({
  title: options.title || 'Machine',
  dataIndex: 'machineName',
  key: 'machineName',
  width: 180,
  sorter:
    options.sorter !== false
      ? (a, b) => (a.machineName || '').localeCompare(b.machineName || '')
      : undefined,
  render: options.render,
});

/**
 * Status column with optional badge rendering
 */
export const statusColumn = <T extends { status?: string }>(
  options: Parameters<ColumnFactory<T>>[0] = {}
): ColumnsType<T>[number] => ({
  title: options.title || 'Status',
  dataIndex: 'status',
  key: 'status',
  width: 120,
  sorter:
    options.sorter !== false ? (a, b) => (a.status || '').localeCompare(b.status || '') : undefined,
  render: options.render,
});

/**
 * Created date column
 */
export const createdDateColumn = <T extends { createdDate?: string | number | Date }>(
  options: Parameters<ColumnFactory<T>>[0] = {}
): ColumnsType<T>[number] => ({
  title: options.title || 'Created',
  dataIndex: 'createdDate',
  key: 'createdDate',
  width: 180,
  sorter:
    options.sorter !== false
      ? (a, b) => new Date(a.createdDate || 0).getTime() - new Date(b.createdDate || 0).getTime()
      : undefined,
  render: options.render || ((value: string) => (value ? new Date(value).toLocaleString() : '-')),
});

/**
 * Updated date column
 */
export const updatedDateColumn = <T extends { updatedDate?: string | number | Date }>(
  options: Parameters<ColumnFactory<T>>[0] = {}
): ColumnsType<T>[number] => ({
  title: options.title || 'Updated',
  dataIndex: 'updatedDate',
  key: 'updatedDate',
  width: 180,
  sorter:
    options.sorter !== false
      ? (a, b) => new Date(a.updatedDate || 0).getTime() - new Date(b.updatedDate || 0).getTime()
      : undefined,
  render: options.render || ((value: string) => (value ? new Date(value).toLocaleString() : '-')),
});

/**
 * Actions column (typically used for edit/delete buttons)
 * This is just a shell - you provide the render function
 */
export const actionsColumn = <T,>(
  render: (record: T) => React.ReactNode,
  options: { width?: number; fixed?: 'left' | 'right' } = {}
): ColumnsType<T>[number] => ({
  title: 'Actions',
  key: 'actions',
  width: options.width || 120,
  fixed: options.fixed,
  render: (_, record) => render(record),
});

/**
 * Numeric count column (e.g., repository count, machine count)
 */
export const countColumn = <T extends { count?: number }>(
  options: Parameters<ColumnFactory<T>>[0] = {}
): ColumnsType<T>[number] => ({
  title: options.title || 'Count',
  dataIndex: 'count',
  key: 'count',
  width: 100,
  align: 'center' as const,
  sorter: options.sorter !== false ? (a, b) => (a.count || 0) - (b.count || 0) : undefined,
  render: options.render || ((value: number) => value ?? 0),
});

/**
 * Priority column
 */
export const priorityColumn = <T extends { priority?: number }>(
  options: Parameters<ColumnFactory<T>>[0] = {}
): ColumnsType<T>[number] => ({
  title: options.title || 'Priority',
  dataIndex: 'priority',
  key: 'priority',
  width: 100,
  align: 'center' as const,
  sorter: options.sorter !== false ? (a, b) => (a.priority || 0) - (b.priority || 0) : undefined,
  render: options.render,
});

/**
 * Create a standard set of columns commonly used in resource tables
 */
export function createResourceColumns<T extends { teamName?: string; createdDate?: string }>(
  nameColumn: ColumnsType<T>[number],
  additionalColumns: ColumnsType<T> = []
): ColumnsType<T> {
  return [nameColumn, teamNameColumn<T>(), ...additionalColumns, createdDateColumn<T>()];
}

export interface ActionMenuItem<T> {
  key: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  danger?: boolean;
  onClick: (record: T) => void;
}

export interface ActionColumnOptions<T> {
  title?: React.ReactNode;
  width?: number;
  fixed?: 'start' | 'end';
  buttonIcon?: React.ReactNode;
  buttonLabel?: React.ReactNode;
  onView?: (record: T) => void;
  onEdit?: (record: T) => void;
  onDelete?: (record: T) => void;
  getMenuItems?: (record: T) => ActionMenuItem<T>[];
  renderActions?: (record: T) => React.ReactNode;
}

/**
 * Create a reusable actions column with a dropdown menu
 */
export const createActionColumn = <T,>(
  options: ActionColumnOptions<T>
): ColumnsType<T>[number] => ({
  title: options.title || i18n.t('common:actionsColumn', { defaultValue: 'Actions' }),
  key: 'actions',
  width: options.width || 120,
  fixed: options.fixed,
  render: (_: unknown, record: T) => {
    if (options.renderActions) {
      return options.renderActions(record);
    }

    const baseItems: ActionMenuItem<T>[] = [];
    if (options.onView) {
      baseItems.push({
        key: 'view',
        label: i18n.t('common:viewDetails'),
        icon: <EyeOutlined />,
        onClick: options.onView,
      });
    }
    if (options.onEdit) {
      baseItems.push({
        key: 'edit',
        label: i18n.t('common:actions.edit'),
        icon: <EditOutlined />,
        onClick: options.onEdit,
      });
    }
    if (options.onDelete) {
      baseItems.push({
        key: 'delete',
        label: i18n.t('common:actions.delete'),
        icon: <DeleteOutlined />,
        danger: true,
        onClick: options.onDelete,
      });
    }

    const extraItems = options.getMenuItems?.(record) || [];
    const items = [...baseItems, ...extraItems];

    if (!items.length) {
      return null;
    }

    const handlers: Record<string, (rec: T) => void> = {};
    const menuItems = items.map(({ key, label, icon, danger, onClick }) => {
      handlers[key] = onClick;
      return {
        key,
        label,
        icon,
        danger,
      };
    });

    const menu: MenuProps = {
      items: menuItems,
      onClick: ({ key }) => {
        handlers[key]?.(record);
      },
    };

    return (
      <RediaccDropdown menu={menu} trigger={['click']}>
        <RediaccButton icon={options.buttonIcon || <MoreOutlined />}>
          {options.buttonLabel}
        </RediaccButton>
      </RediaccDropdown>
    );
  },
});

export interface StatusColumnOptions<T> {
  title?: React.ReactNode;
  dataIndex: ColumnDataIndex<T>;
  key?: string;
  width?: number;
  statusMap: Record<string, StatusConfig>;
  defaultConfig?: StatusConfig;
  sorter?: boolean | ColumnsType<T>[number]['sorter'];
  align?: 'left' | 'center' | 'right';
  renderValue?: (value: unknown, record: T) => string;
}

/**
 * Create a status column with icon and tooltip rendering
 */
export const createStatusColumn = <T,>(options: StatusColumnOptions<T>): ColumnsType<T>[number] => {
  const dataIndex = options.dataIndex;
  const dataKey = typeof dataIndex === 'string' ? dataIndex : String(dataIndex);
  const renderStatus = createStatusRenderer<string>(
    options.statusMap as Record<string, StatusConfig>,
    options.defaultConfig
  );

  let sorter: ColumnsType<T>[number]['sorter'] | undefined;
  if (options.sorter === true) {
    sorter = (a: T, b: T) => {
      const aValue = (a as Record<string, unknown>)[dataKey];
      const bValue = (b as Record<string, unknown>)[dataKey];
      return String(aValue ?? '').localeCompare(String(bValue ?? ''));
    };
  } else if (options.sorter) {
    sorter = options.sorter;
  }

  return {
    title: options.title || i18n.t('common:statusColumn', { defaultValue: 'Status' }),
    dataIndex,
    key: options.key || dataKey || 'status',
    width: options.width ?? 100,
    align: options.align ?? 'center',
    sorter,
    render: (value: unknown, record: T) => {
      const statusValue = options.renderValue ? options.renderValue(value, record) : value;
      return renderStatus(String(statusValue ?? ''));
    },
  };
};

const toTimestamp = (value: unknown): number => {
  if (value instanceof Date) {
    return value.getTime();
  }
  if (typeof value === 'string' || typeof value === 'number') {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 0 : date.getTime();
  }
  return 0;
};

export interface DateColumnOptions<T> {
  title?: React.ReactNode;
  dataIndex: ColumnDataIndex<T>;
  key?: string;
  width?: number;
  format?: string;
  sorter?: boolean | ColumnsType<T>[number]['sorter'];
  defaultSortOrder?: ColumnsType<T>[number]['defaultSortOrder'];
  render?: (value: string | Date | null | undefined, record: T) => React.ReactNode;
}

/**
 * Create a date column with shared timestamp formatting
 */
export const createDateColumn = <T,>(options: DateColumnOptions<T>): ColumnsType<T>[number] => {
  const dataIndex = options.dataIndex;
  const dataKey = typeof dataIndex === 'string' ? dataIndex : String(dataIndex);
  const fallbackTitle = i18n.t('common:dateColumn', { defaultValue: 'Date' });

  let sorter: ColumnsType<T>[number]['sorter'] | undefined;
  if (options.sorter === true || options.sorter === undefined) {
    sorter = (a: T, b: T) => {
      const aValue = (a as Record<string, unknown>)[dataKey];
      const bValue = (b as Record<string, unknown>)[dataKey];
      return toTimestamp(aValue) - toTimestamp(bValue);
    };
  } else if (options.sorter === false) {
    sorter = undefined;
  } else {
    sorter = options.sorter;
  }

  return {
    title: options.title || fallbackTitle,
    dataIndex,
    key: options.key || dataKey || 'date',
    width: options.width ?? 180,
    sorter,
    defaultSortOrder: options.defaultSortOrder,
    render: (value: string | Date | null | undefined, record: T) =>
      options.render
        ? options.render(value, record)
        : renderTimestampElement(value, options.format),
  };
};

export interface TruncatedColumnOptions<T> {
  title: React.ReactNode;
  dataIndex: ColumnDataIndex<T>;
  key?: string;
  width?: number;
  maxLength?: number;
  ellipsis?: boolean;
  tooltipPlacement?: TooltipProps['placement'];
  renderText?: (value: string | null | undefined, record: T) => string | null | undefined;
  renderWrapper?: (content: React.ReactNode, fullText: string) => React.ReactNode;
  sorter?: ColumnsType<T>[number]['sorter'];
}

/**
 * Create a truncated text column with tooltip support
 */
export const createTruncatedColumn = <T,>(
  options: TruncatedColumnOptions<T>
): ColumnsType<T>[number] => {
  const dataIndex = options.dataIndex;
  const dataKey = typeof dataIndex === 'string' ? dataIndex : String(dataIndex);
  const maxLength = options.maxLength ?? 12;
  const placement = options.tooltipPlacement || 'topLeft';

  return {
    title: options.title,
    dataIndex,
    key: options.key || dataKey || 'value',
    width: options.width,
    ellipsis: options.ellipsis ?? true,
    sorter: options.sorter,
    render: (value: string | null | undefined, record: T) => {
      const resolvedValue = options.renderText ? options.renderText(value, record) : value;
      if (!resolvedValue) {
        return <RediaccText color="secondary">-</RediaccText>;
      }
      const shouldTruncate = resolvedValue.length > maxLength;
      const displayText = shouldTruncate
        ? `${resolvedValue.slice(0, maxLength)}...`
        : resolvedValue;

      const content = shouldTruncate ? (
        <RediaccTooltip title={resolvedValue} placement={placement}>
          <span>{displayText}</span>
        </RediaccTooltip>
      ) : (
        <span>{displayText}</span>
      );

      return options.renderWrapper ? options.renderWrapper(content, resolvedValue) : content;
    },
  };
};

export interface CountColumnOptions<T> {
  title: React.ReactNode;
  dataIndex: ColumnDataIndex<T>;
  key?: string;
  width?: number;
  align?: 'left' | 'center' | 'right';
  sorter?: boolean | ColumnsType<T>[number]['sorter'];
  icon?: React.ReactNode;
  useBadge?: boolean;
  showZero?: boolean;
  renderValue?: (value: number, record: T) => React.ReactNode;
}

/**
 * Create a count column with optional badge or icon rendering
 */
export const createCountColumn = <T,>(options: CountColumnOptions<T>): ColumnsType<T>[number] => {
  const dataIndex = options.dataIndex;
  const dataKey = typeof dataIndex === 'string' ? dataIndex : String(dataIndex);

  let sorter: ColumnsType<T>[number]['sorter'] | undefined;
  if (options.sorter === true) {
    sorter = (a: T, b: T) => {
      const aValue = (a as Record<string, unknown>)[dataKey];
      const bValue = (b as Record<string, unknown>)[dataKey];
      return Number(aValue ?? 0) - Number(bValue ?? 0);
    };
  } else if (options.sorter) {
    sorter = options.sorter;
  }

  return {
    title: options.title,
    dataIndex,
    key: options.key || dataKey || 'count',
    width: options.width ?? 100,
    align: options.align ?? 'center',
    sorter,
    render: (value: number, record: T) => {
      if (options.renderValue) {
        return options.renderValue(value, record);
      }

      const count = value ?? 0;

      if (options.useBadge) {
        return (
          <RediaccTooltip title={options.title}>
            <Space size="small">
              {options.icon}
              <span>{count}</span>
            </Space>
          </RediaccTooltip>
        );
      }

      return (
        <Space size="small">
          {options.icon}
          <span>{count}</span>
        </Space>
      );
    },
  };
};

export interface VersionColumnOptions<T> {
  title?: React.ReactNode;
  dataIndex: ColumnDataIndex<T>;
  key?: string;
  width?: number;
  align?: 'left' | 'center' | 'right';
  sorter?: boolean | ColumnsType<T>[number]['sorter'];
  formatVersion?: (version: number) => string;
  renderValue?: (value: number, record: T) => React.ReactNode;
}

/**
 * Create a version column with consistent Tag rendering
 */
export const createVersionColumn = <T,>(
  options: VersionColumnOptions<T>
): ColumnsType<T>[number] => {
  const dataIndex = options.dataIndex;
  const dataKey = typeof dataIndex === 'string' ? dataIndex : String(dataIndex);
  const fallbackTitle = i18n.t('common:general.vaultVersion', { defaultValue: 'Version' });

  let sorter: ColumnsType<T>[number]['sorter'] | undefined;
  if (options.sorter === true || options.sorter === undefined) {
    sorter = (a: T, b: T) => {
      const aValue = (a as Record<string, unknown>)[dataKey];
      const bValue = (b as Record<string, unknown>)[dataKey];
      return Number(aValue ?? 0) - Number(bValue ?? 0);
    };
  } else if (options.sorter === false) {
    sorter = undefined;
  } else {
    sorter = options.sorter;
  }

  return {
    title: options.title || fallbackTitle,
    dataIndex,
    key: options.key || dataKey || 'version',
    width: options.width ?? 120,
    align: options.align ?? 'center',
    sorter,
    render: (value: number, record: T) => {
      if (options.renderValue) {
        return options.renderValue(value, record);
      }

      if (value === null || value === undefined) {
        return <RediaccText color="secondary">-</RediaccText>;
      }

      const formattedVersion = options.formatVersion
        ? options.formatVersion(value)
        : i18n.t('common:general.versionFormat', { defaultValue: 'v{{version}}', version: value });

      return <VersionTag>{formattedVersion}</VersionTag>;
    },
  };
};
