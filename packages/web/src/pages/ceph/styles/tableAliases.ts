/**
 * Shared table component aliases for Ceph tables.
 * Centralizes common re-exports to avoid duplication across table styles.
 *
 * Updated to use the new RediaccTable UI component.
 */

export { InlineStack as ActionsRow } from '@/components/common/styled';
export {
  TableCellContent as NameCell,
  TableCellText as NameText,
  TableWrapper,
} from '@/components/ui/Table';
// Re-export ExpandIcon from primitives (not table-specific)
export { ExpandIcon } from '@/styles/primitives';
