import React, { useCallback, useMemo, useRef, useEffect } from 'react';
import { Space } from 'antd';
import { List as ReactWindowList } from 'react-window';
import * as InfiniteLoaderModule from 'react-window-infinite-loader';
import InlineLoadingIndicator from '@/components/common/InlineLoadingIndicator';
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell';
import { RediaccCheckbox } from '@/components/ui';
import { useTableStyles } from '@/hooks/useComponentStyles';
import { useMachineSelection } from '@/store/ceph/hooks';
import { Machine } from '@/types';
import styles from './VirtualMachineTable.module.css';

type ScrollAlign = 'auto' | 'smart' | 'center' | 'end' | 'start';

interface VirtualizedListHandle {
  scrollToItem: (index: number, align?: ScrollAlign) => void;
}

type ListChildProps<T> = {
  index: number;
  style: React.CSSProperties;
  data: T;
};

type OnItemsRendered = (info: {
  overscanStartIndex: number;
  overscanStopIndex: number;
  visibleStartIndex: number;
  visibleStopIndex: number;
}) => void;

type BaseListProps = Record<string, unknown>;
const BaseListComponent = ReactWindowList as unknown as React.ComponentType<BaseListProps>;

interface VirtualListProps {
  height: number;
  width: number | string;
  itemCount: number;
  itemSize: number;
  overscanCount?: number;
  onItemsRendered?: OnItemsRendered;
  itemData: VirtualMachineListRowProps;
  children: React.ComponentType<ListChildProps<VirtualMachineListRowProps>>;
  'data-testid'?: string;
}

const List = React.forwardRef<VirtualizedListHandle, VirtualListProps>((props, ref) => {
  const { children, ...rest } = props;
  return (
    <BaseListComponent {...rest} ref={ref as React.Ref<unknown>}>
      {children as unknown}
    </BaseListComponent>
  );
});
List.displayName = 'VirtualMachineList';

type InfiniteLoaderComponentProps = {
  isItemLoaded: (index: number) => boolean;
  itemCount: number;
  loadMoreItems: (startIndex: number, stopIndex: number) => Promise<void> | void;
  children: (props: {
    onItemsRendered: OnItemsRendered;
    ref: (instance: VirtualizedListHandle | null) => void;
  }) => React.ReactNode;
};

const infiniteLoaderModule = InfiniteLoaderModule as unknown as {
  InfiniteLoader?: React.ComponentType<InfiniteLoaderComponentProps>;
  default?: React.ComponentType<InfiniteLoaderComponentProps>;
};

const InfiniteLoader =
  infiniteLoaderModule.InfiniteLoader ?? infiniteLoaderModule.default ?? (() => null);

interface VirtualMachineTableProps {
  machines: Machine[];
  loading?: boolean;
  hasMore?: boolean;
  loadMore?: () => Promise<void>;
  rowHeight?: number;
  height?: number;
  selectable?: boolean;
  onRowClick?: (machine: Machine) => void;
  renderActions?: (machine: Machine) => React.ReactNode;
}

interface RowData {
  machine: Machine;
  index: number;
  style: React.CSSProperties;
}

interface VirtualMachineListRowProps {
  machines: Machine[];
  isItemLoaded: (index: number) => boolean;
  selectable: boolean;
  onRowClick?: (machine: Machine) => void;
  renderActions?: (machine: Machine) => React.ReactNode;
}

const MachineRow: React.FC<
  RowData & {
    selectable: boolean;
    onRowClick?: (machine: Machine) => void;
    renderActions?: (machine: Machine) => React.ReactNode;
  }
> = ({ machine, style, selectable, onRowClick, renderActions }) => {
  const { isMachineSelected, toggleSelection } = useMachineSelection();
  const isSelected = isMachineSelected(machine.machineName);
  const tableStyles = useTableStyles();

  const handleCheckboxChange = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      toggleSelection(machine.machineName);
    },
    [machine.machineName, toggleSelection]
  );

  const handleRowClick = useCallback(() => {
    if (onRowClick) {
      onRowClick(machine);
    }
  }, [machine, onRowClick]);

  return (
    <div
      style={{
        ...style,
        ...tableStyles.tableCell,
        cursor: onRowClick ? 'pointer' : 'default',
        borderBottom: '1px solid var(--color-border-secondary)',
        transition: 'background-color 0.2s ease',
      }}
      className={styles.row}
      onClick={handleRowClick}
      data-testid={`virtual-machine-row-${machine.machineName}`}
    >
      <Space className={styles.rowContent}>
        {selectable && (
          <RediaccCheckbox
            checked={isSelected}
            onClick={handleCheckboxChange}
            data-testid={`virtual-machine-checkbox-${machine.machineName}`}
          />
        )}
        <div
          className={styles.machineName}
          data-testid={`virtual-machine-name-${machine.machineName}`}
        >
          {machine.machineName}
        </div>
        <div className={styles.teamName}>{machine.teamName}</div>
        <div data-testid={`virtual-machine-status-${machine.machineName}`}>
          <MachineAssignmentStatusCell machine={machine} />
        </div>
        {renderActions && (
          <div
            className={styles.actions}
            data-testid={`virtual-machine-actions-${machine.machineName}`}
          >
            {renderActions(machine)}
          </div>
        )}
      </Space>
    </div>
  );
};

export const VirtualMachineTable: React.FC<VirtualMachineTableProps> = ({
  machines,
  loading = false,
  hasMore = false,
  loadMore,
  rowHeight = 64,
  height = 600,
  selectable = true,
  onRowClick,
  renderActions,
}) => {
  const listRef = useRef<VirtualizedListHandle | null>(null);
  const setListRef = useCallback((instance: VirtualizedListHandle | null) => {
    listRef.current = instance;
  }, []);
  const { selectedMachines } = useMachineSelection();
  const tableStyles = useTableStyles();

  // Create items list with potential placeholders for infinite loading
  const itemCount = hasMore ? machines.length + 1 : machines.length;

  // Check if an item is loaded
  const isItemLoaded = useCallback(
    (index: number) => {
      return !hasMore || index < machines.length;
    },
    [hasMore, machines.length]
  );

  // Load more items
  const loadMoreItems = useCallback(async () => {
    if (loadMore && !loading) {
      await loadMore();
    }
  }, [loadMore, loading]);

  // Render a single row
  const RowComponent = useCallback<React.ComponentType<ListChildProps<VirtualMachineListRowProps>>>(
    ({ index, style, data }) => {
      const {
        machines: rowMachines,
        isItemLoaded: rowIsItemLoaded,
        selectable: rowSelectable,
        onRowClick: rowOnRowClick,
        renderActions: rowRenderActions,
      } = data;

      if (!rowIsItemLoaded(index)) {
        return (
          <div
            style={style}
            className={styles.loadingRow}
            data-testid="virtual-machine-row-loading"
          >
            <InlineLoadingIndicator
              width="90%"
              height={24}
              data-testid="virtual-machine-row-loading-indicator"
            />
          </div>
        );
      }

      const machine = rowMachines[index];
      return (
        <MachineRow
          machine={machine}
          index={index}
          style={style}
          selectable={rowSelectable}
          onRowClick={rowOnRowClick}
          renderActions={rowRenderActions}
        />
      );
    },
    []
  );

  const rowProps = useMemo<VirtualMachineListRowProps>(
    () => ({
      machines,
      isItemLoaded,
      selectable,
      onRowClick,
      renderActions,
    }),
    [machines, isItemLoaded, selectable, onRowClick, renderActions]
  );

  // Scroll to top when machines change significantly
  useEffect(() => {
    if (listRef.current && machines.length > 0) {
      listRef.current.scrollToItem(0, 'start');
    }
  }, [machines.length]);

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!listRef.current) return;

      const currentIndex =
        selectedMachines.length > 0
          ? machines.findIndex((m) => m.machineName === selectedMachines[0])
          : 0;

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          if (currentIndex < machines.length - 1) {
            listRef.current.scrollToItem(currentIndex + 1, 'smart');
          }
          break;
        case 'ArrowUp':
          e.preventDefault();
          if (currentIndex > 0) {
            listRef.current.scrollToItem(currentIndex - 1, 'smart');
          }
          break;
      }
    },
    [selectedMachines, machines]
  );

  const content = useMemo(() => {
    if (loadMore && hasMore) {
      // Use InfiniteLoader to lazily fetch additional rows as the user scrolls
      return (
        <InfiniteLoader
          isItemLoaded={isItemLoaded}
          itemCount={itemCount}
          loadMoreItems={() => loadMoreItems()}
        >
          {({
            onItemsRendered,
            ref,
          }: {
            onItemsRendered: OnItemsRendered;
            ref: (instance: VirtualizedListHandle | null) => void;
          }) => {
            const combinedRef = (instance: VirtualizedListHandle | null) => {
              setListRef(instance);
              ref(instance);
            };
            return (
              <List
                height={height}
                width="100%"
                itemCount={itemCount}
                itemSize={rowHeight}
                overscanCount={5}
                onItemsRendered={onItemsRendered}
                itemData={rowProps}
                ref={combinedRef}
                data-testid="virtual-machine-list"
              >
                {RowComponent}
              </List>
            );
          }}
        </InfiniteLoader>
      );
    }

    return (
      <List
        height={height}
        width="100%"
        itemCount={machines.length}
        itemSize={rowHeight}
        overscanCount={5}
        itemData={rowProps}
        ref={setListRef}
        data-testid="virtual-machine-list"
      >
        {RowComponent}
      </List>
    );
  }, [
    loadMore,
    hasMore,
    isItemLoaded,
    itemCount,
    loadMoreItems,
    height,
    rowHeight,
    RowComponent,
    rowProps,
    machines.length,
    setListRef,
  ]);

  return (
    <div
      style={{
        ...tableStyles.tableContainer,
      }}
      className={styles.virtualTable}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      data-testid="virtual-machine-table"
    >
      <div
        style={{
          ...tableStyles.tableHeader,
          position: 'sticky',
          top: 0,
          zIndex: 1,
          borderBottom: '1px solid var(--color-border-secondary)',
        }}
        className={styles.header}
        data-testid="virtual-machine-header"
      >
        <Space className={styles.headerContent}>
          {selectable && <div className={styles.checkboxColumn} />}
          <div className={styles.machineName}>Machine Name</div>
          <div className={styles.teamName}>Team</div>
          <div className={styles.status}>Assignment Status</div>
          {renderActions && <div className={styles.actions}>Actions</div>}
        </Space>
      </div>
      <div data-testid="virtual-machine-keyboard-navigation">{content}</div>
    </div>
  );
};
