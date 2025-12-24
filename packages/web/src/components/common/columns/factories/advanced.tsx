import React from 'react';
import { Space, Tag, Tooltip, Typography } from 'antd';
import i18n from '@/i18n/config';
import { createStatusRenderer, renderTimestampElement, type StatusConfig } from '../renderers';
import type {
  CountColumnOptions,
  DateColumnOptions,
  StatusColumnOptions,
  TruncatedColumnOptions,
  VersionColumnOptions,
} from '../types';
import type { ColumnsType } from 'antd/es/table';

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
    title: options.title || i18n.t('common:statusColumn'),
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

/**
 * Create a date column with shared timestamp formatting
 */
export const createDateColumn = <T,>(options: DateColumnOptions<T>): ColumnsType<T>[number] => {
  const dataIndex = options.dataIndex;
  const dataKey = typeof dataIndex === 'string' ? dataIndex : String(dataIndex);
  const fallbackTitle = i18n.t('common:dateColumn');

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
        return <Typography.Text>-</Typography.Text>;
      }
      const shouldTruncate = resolvedValue.length > maxLength;
      const displayText = shouldTruncate
        ? `${resolvedValue.slice(0, maxLength)}...`
        : resolvedValue;

      const content = shouldTruncate ? (
        <Tooltip title={resolvedValue} placement={placement}>
          <Typography.Text>{displayText}</Typography.Text>
        </Tooltip>
      ) : (
        <Typography.Text>{displayText}</Typography.Text>
      );

      return options.renderWrapper ? options.renderWrapper(content, resolvedValue) : content;
    },
  };
};

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
          <Tooltip title={options.title}>
            <Space size="small">
              {options.icon}
              <Typography.Text>{count}</Typography.Text>
            </Space>
          </Tooltip>
        );
      }

      return (
        <Space size="small">
          {options.icon}
          <Typography.Text>{count}</Typography.Text>
        </Space>
      );
    },
  };
};

/**
 * Create a version column with consistent Tag rendering
 */
export const createVersionColumn = <T,>(
  options: VersionColumnOptions<T>
): ColumnsType<T>[number] => {
  const dataIndex = options.dataIndex;
  const dataKey = typeof dataIndex === 'string' ? dataIndex : String(dataIndex);
  const fallbackTitle = i18n.t('common:general.vaultVersion');

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
        return <Typography.Text>-</Typography.Text>;
      }

      const formattedVersion = options.formatVersion
        ? options.formatVersion(value)
        : i18n.t('common:general.versionFormat', { version: value });

      return <Tag>{formattedVersion}</Tag>;
    },
  };
};
