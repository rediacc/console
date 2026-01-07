import type { StatusConfig } from './renderers';
import type { Breakpoint, TooltipProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';

export type ColumnDataIndex = string;

// Type for column factory functions
export type ColumnFactory<T> = (options?: {
  title?: string;
  sorter?: boolean;
  filterable?: boolean;
  render?: (value: string, record: T) => React.ReactNode;
}) => ColumnsType<T>[number];

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
  fixed?: 'left' | 'right';
  buttonIcon?: React.ReactNode;
  buttonLabel?: React.ReactNode;
  onView?: (record: T) => void;
  onEdit?: (record: T) => void;
  onDelete?: (record: T) => void;
  getMenuItems?: (record: T) => ActionMenuItem<T>[];
  renderActions?: (record: T) => React.ReactNode;
  responsive?: Breakpoint[];
}

export interface StatusColumnOptions<T> {
  title?: React.ReactNode;
  dataIndex: ColumnDataIndex;
  key?: string;
  width?: number;
  statusMap: Record<string, StatusConfig>;
  defaultConfig?: StatusConfig;
  sorter?: boolean | ColumnsType<T>[number]['sorter'];
  align?: 'left' | 'center' | 'right';
  renderValue?: (value: unknown, record: T) => string;
}

export interface DateColumnOptions<T> {
  title?: React.ReactNode;
  dataIndex: ColumnDataIndex;
  key?: string;
  width?: number;
  format?: string;
  sorter?: boolean | ColumnsType<T>[number]['sorter'];
  defaultSortOrder?: ColumnsType<T>[number]['defaultSortOrder'];
  render?: (value: string | Date | null | undefined, record: T) => React.ReactNode;
}

export interface TruncatedColumnOptions<T> {
  title: React.ReactNode;
  dataIndex: ColumnDataIndex;
  key?: string;
  width?: number;
  maxLength?: number;
  ellipsis?: boolean;
  tooltipPlacement?: TooltipProps['placement'];
  renderText?: (value: string | null | undefined, record: T) => string | null | undefined;
  renderWrapper?: (content: React.ReactNode, fullText: string) => React.ReactNode;
  sorter?: ColumnsType<T>[number]['sorter'];
}

export interface CountColumnOptions<T> {
  title: React.ReactNode;
  dataIndex: ColumnDataIndex;
  key?: string;
  width?: number;
  align?: 'left' | 'center' | 'right';
  sorter?: boolean | ColumnsType<T>[number]['sorter'];
  icon?: React.ReactNode;
  useBadge?: boolean;
  showZero?: boolean;
  renderValue?: (value: number, record: T) => React.ReactNode;
}

export interface VersionColumnOptions<T> {
  title?: React.ReactNode;
  dataIndex: ColumnDataIndex;
  key?: string;
  width?: number;
  align?: 'left' | 'center' | 'right';
  sorter?: boolean | ColumnsType<T>[number]['sorter'];
  formatVersion?: (version: number) => string;
  renderValue?: (value: number, record: T) => React.ReactNode;
}
