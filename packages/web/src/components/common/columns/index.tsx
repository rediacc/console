/**
 * Shared table column definitions to ensure consistency across pages
 * Import specific columns or use the factories to create customized versions
 */

// Re-export types
export type {
  ActionColumnOptions,
  ActionMenuItem,
  ColumnDataIndex,
  ColumnFactory,
  CountColumnOptions,
  DateColumnOptions,
  StatusColumnOptions,
  TruncatedColumnOptions,
  VersionColumnOptions,
} from './types';

// Re-export simple column factories
export {
  actionsColumn,
  bridgeNameColumn,
  countColumn,
  createdDateColumn,
  createResourceColumns,
  machineNameColumn,
  priorityColumn,
  statusColumn,
  teamNameColumn,
  updatedDateColumn,
} from './factories/simple';

// Re-export action column factory
export { createActionColumn } from './factories/action';

// Re-export advanced column factories
export {
  createCountColumn,
  createDateColumn,
  createStatusColumn,
  createTruncatedColumn,
  createVersionColumn,
} from './factories/advanced';

// Re-export renderers
export { createStatusRenderer, renderTimestampElement, type StatusConfig } from './renderers';
