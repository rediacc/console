import type { TableProps } from 'antd';
import { Table } from 'antd';

interface ModalTableProps<T> extends Omit<TableProps<T>, 'pagination'> {
  /** Maximum height for the scrollable area. Defaults to 300. */
  maxHeight?: number;
}

/**
 * Pre-configured Table for use inside modals.
 * - Pagination disabled
 * - Horizontal scroll enabled
 * - Vertical scroll with configurable max height
 */
function ModalTable<T extends object>({ maxHeight = 300, scroll, ...props }: ModalTableProps<T>) {
  return (
    <Table<T>
      pagination={false}
      scroll={{ x: 'max-content', y: maxHeight, ...scroll }}
      {...props}
    />
  );
}

export default ModalTable;
