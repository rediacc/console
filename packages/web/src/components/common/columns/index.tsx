/**
 * Shared table column definitions to ensure consistency across pages
 * Import specific columns or use the factories to create customized versions
 */

// Re-export constants
export { RESPONSIVE_HIDE_XS } from './constants';

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

// Legacy simple column factories have been removed from ./factories/simple.ts.
// Use the advanced column factories below which provide better configurability.

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

// Re-export renderers (StatusConfig type needed by consumers)
export { type StatusConfig } from './renderers';
