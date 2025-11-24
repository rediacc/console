import React from 'react'
import type { ColumnsType } from 'antd/es/table'

/**
 * Shared table column definitions to ensure consistency across pages
 * Import specific columns or use the factories to create customized versions
 */

// Type for column factory functions
type ColumnFactory<T> = (options?: {
  title?: string
  sorter?: boolean
  filterable?: boolean
  render?: (value: string, record: T) => React.ReactNode
}) => ColumnsType<T>[number]

/**
 * Team name column - used across machines, credentials, storage, etc.
 */
export const teamNameColumn: ColumnFactory<any> = (options = {}) => ({
  title: options.title || 'Team',
  dataIndex: 'teamName',
  key: 'teamName',
  width: 150,
  sorter: options.sorter !== false
    ? (a, b) => (a.teamName || '').localeCompare(b.teamName || '')
    : undefined,
  render: options.render
})

/**
 * Bridge name column
 */
export const bridgeNameColumn: ColumnFactory<any> = (options = {}) => ({
  title: options.title || 'Bridge',
  dataIndex: 'bridgeName',
  key: 'bridgeName',
  width: 150,
  sorter: options.sorter !== false
    ? (a, b) => (a.bridgeName || '').localeCompare(b.bridgeName || '')
    : undefined,
  render: options.render
})

/**
 * Machine name column
 */
export const machineNameColumn: ColumnFactory<any> = (options = {}) => ({
  title: options.title || 'Machine',
  dataIndex: 'machineName',
  key: 'machineName',
  width: 180,
  sorter: options.sorter !== false
    ? (a, b) => (a.machineName || '').localeCompare(b.machineName || '')
    : undefined,
  render: options.render
})

/**
 * Status column with optional badge rendering
 */
export const statusColumn: ColumnFactory<any> = (options = {}) => ({
  title: options.title || 'Status',
  dataIndex: 'status',
  key: 'status',
  width: 120,
  sorter: options.sorter !== false
    ? (a, b) => (a.status || '').localeCompare(b.status || '')
    : undefined,
  render: options.render
})

/**
 * Created date column
 */
export const createdDateColumn: ColumnFactory<any> = (options = {}) => ({
  title: options.title || 'Created',
  dataIndex: 'createdDate',
  key: 'createdDate',
  width: 180,
  sorter: options.sorter !== false
    ? (a, b) => new Date(a.createdDate || 0).getTime() - new Date(b.createdDate || 0).getTime()
    : undefined,
  render: options.render || ((value: string) =>
    value ? new Date(value).toLocaleString() : '-'
  )
})

/**
 * Updated date column
 */
export const updatedDateColumn: ColumnFactory<any> = (options = {}) => ({
  title: options.title || 'Updated',
  dataIndex: 'updatedDate',
  key: 'updatedDate',
  width: 180,
  sorter: options.sorter !== false
    ? (a, b) => new Date(a.updatedDate || 0).getTime() - new Date(b.updatedDate || 0).getTime()
    : undefined,
  render: options.render || ((value: string) =>
    value ? new Date(value).toLocaleString() : '-'
  )
})

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
  render: (_, record) => render(record)
})

/**
 * Numeric count column (e.g., repository count, machine count)
 */
export const countColumn: ColumnFactory<any> = (options = {}) => ({
  title: options.title || 'Count',
  dataIndex: 'count',
  key: 'count',
  width: 100,
  align: 'center' as const,
  sorter: options.sorter !== false
    ? (a, b) => (a.count || 0) - (b.count || 0)
    : undefined,
  render: options.render || ((value: number) => value ?? 0)
})

/**
 * Priority column
 */
export const priorityColumn: ColumnFactory<any> = (options = {}) => ({
  title: options.title || 'Priority',
  dataIndex: 'priority',
  key: 'priority',
  width: 100,
  align: 'center' as const,
  sorter: options.sorter !== false
    ? (a, b) => (a.priority || 0) - (b.priority || 0)
    : undefined,
  render: options.render
})

/**
 * Create a standard set of columns commonly used in resource tables
 */
export function createResourceColumns<T extends { teamName?: string; createdDate?: string }>(
  nameColumn: ColumnsType<T>[number],
  additionalColumns: ColumnsType<T> = []
): ColumnsType<T> {
  return [
    nameColumn,
    teamNameColumn() as ColumnsType<T>[number],
    ...additionalColumns,
    createdDateColumn() as ColumnsType<T>[number]
  ]
}
