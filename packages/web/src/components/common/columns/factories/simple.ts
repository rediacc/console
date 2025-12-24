import React from 'react';
import type { ColumnFactory } from '../types';
import type { ColumnsType } from 'antd/es/table';

/**
 * Shared table column definitions to ensure consistency across pages
 * Import specific columns or use the factories to create customized versions
 */

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
export const actionsColumn = <T>(
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
