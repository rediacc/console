/**
 * Column Builder Utilities - Index
 *
 * Re-exports all column builder utilities for convenient importing.
 * These utilities standardize table column definitions across the application.
 *
 * @example
 * ```tsx
 * import { createStatusColumn, createPriorityColumn } from '@/utils/columnBuilders';
 *
 * const columns = [
 *   createStatusColumn<QueueItem>({
 *     dataIndex: 'status',
 *     statusMap: { ... },
 *   }),
 *   createPriorityColumn<QueueItem>({
 *     dataIndex: 'priority',
 *   }),
 * ];
 * ```
 */

export {
  createStatusColumn,
  createPriorityColumn,
  createTimestampColumn,
  createTruncatedColumn,
  createActionsColumn,
  createAgeColumn,
  createResourceNameColumn,
  DEFAULT_PRIORITY_LABELS,
  PRIORITY_ICONS,
  QUEUE_STATUS_ICONS,
  type StatusConfig,
  type StatusColumnConfig,
  type PriorityColumnConfig,
  type TimestampColumnConfig,
  type TruncatedColumnConfig,
  type ActionsColumnConfig,
  type ActionItem,
  type AgeColumnConfig,
  type ResourceNameColumnConfig,
} from '../columnBuilders.tsx';
