import React, { useCallback, useMemo, useRef, useEffect } from 'react'
import { FixedSizeList as List } from 'react-window'
import * as InfiniteLoaderModule from 'react-window-infinite-loader'
import { Checkbox, Space, Spin } from 'antd'
import { Machine } from '@/types'
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell'
import { useMachineSelection } from '@/store/distributedStorage/hooks'
import { useTableStyles } from '@/hooks/useComponentStyles'
import styles from './VirtualMachineTable.module.css'

interface VirtualMachineTableProps {
  machines: Machine[]
  loading?: boolean
  hasMore?: boolean
  loadMore?: () => Promise<void>
  rowHeight?: number
  height?: number
  selectable?: boolean
  onRowClick?: (machine: Machine) => void
  renderActions?: (machine: Machine) => React.ReactNode
}

interface RowData {
  machine: Machine
  index: number
  style: React.CSSProperties
}

const MachineRow: React.FC<RowData & {
  selectable: boolean
  onRowClick?: (machine: Machine) => void
  renderActions?: (machine: Machine) => React.ReactNode
}> = ({ machine, style, selectable, onRowClick, renderActions }) => {
  const { isMachineSelected, toggleSelection } = useMachineSelection()
  const isSelected = isMachineSelected(machine.machineName)
  const tableStyles = useTableStyles()

  const handleCheckboxChange = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    toggleSelection(machine.machineName)
  }, [machine.machineName, toggleSelection])

  const handleRowClick = useCallback(() => {
    if (onRowClick) {
      onRowClick(machine)
    }
  }, [machine, onRowClick])

  return (
    <div
      style={{
        ...style,
        ...tableStyles.tableCell,
        cursor: onRowClick ? 'pointer' : 'default',
        borderBottom: '1px solid var(--color-border-secondary)',
        transition: 'background-color 0.2s ease'
      }}
      className={styles.row}
      onClick={handleRowClick}
      data-testid={`virtual-machine-row-${machine.machineName}`}
    >
      <Space className={styles.rowContent}>
        {selectable && (
          <Checkbox
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
  )
}

export const VirtualMachineTable: React.FC<VirtualMachineTableProps> = ({
  machines,
  loading = false,
  hasMore = false,
  loadMore,
  rowHeight = 64,
  height = 600,
  selectable = true,
  onRowClick,
  renderActions
}) => {
  const listRef = useRef<List>(null)
  const { selectedMachines } = useMachineSelection()
  const tableStyles = useTableStyles()

  // Create items list with potential placeholders for infinite loading
  const itemCount = hasMore ? machines.length + 1 : machines.length
  
  // Check if an item is loaded
  const isItemLoaded = useCallback((index: number) => {
    return !hasMore || index < machines.length
  }, [hasMore, machines.length])

  // Load more items
  const loadMoreItems = useCallback(async () => {
    if (loadMore && !loading) {
      await loadMore()
    }
  }, [loadMore, loading])

  // Render a single row
  const Row = useCallback(({ index, style }: { index: number; style: React.CSSProperties }) => {
    if (!isItemLoaded(index)) {
      return (
        <div 
          style={style} 
          className={styles.loadingRow}
          data-testid="virtual-machine-row-loading"
        >
          <Spin size="small" />
        </div>
      )
    }

    const machine = machines[index]
    return (
      <MachineRow
        key={machine.machineName}
        machine={machine}
        index={index}
        style={style}
        selectable={selectable}
        onRowClick={onRowClick}
        renderActions={renderActions}
      />
    )
  }, [machines, isItemLoaded, selectable, onRowClick, renderActions])

  // Scroll to top when machines change significantly
  useEffect(() => {
    if (listRef.current && machines.length > 0) {
      listRef.current.scrollToItem(0)
    }
  }, [machines.length])

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!listRef.current) return

    const currentIndex = selectedMachines.length > 0 
      ? machines.findIndex(m => m.machineName === selectedMachines[0])
      : 0

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        if (currentIndex < machines.length - 1) {
          listRef.current.scrollToItem(currentIndex + 1)
        }
        break
      case 'ArrowUp':
        e.preventDefault()
        if (currentIndex > 0) {
          listRef.current.scrollToItem(currentIndex - 1)
        }
        break
    }
  }, [selectedMachines, machines])

  const content = useMemo(() => {
    if (loadMore && hasMore) {
      // v1.8.11 API: InfiniteLoader pattern
      const InfiniteLoader = (InfiniteLoaderModule as any).InfiniteLoader
      const renderList = ({ onRowsRendered }: any) => (
        <List
          ref={(list: any) => {
            (listRef as any).current = list
          }}
          height={height}
          itemCount={itemCount}
          itemSize={rowHeight}
          onItemsRendered={onRowsRendered}
          overscanCount={5}
          data-testid="virtual-machine-list"
          width="100%"
        >
          {Row}
        </List>
      )

      return (
        <InfiniteLoader
          isRowLoaded={isItemLoaded}
          rowCount={itemCount}
          loadMoreRows={loadMoreItems}
        >
          {renderList}
        </InfiniteLoader>
      )
    }

    return (
      <List
        ref={listRef}
        height={height}
        itemCount={machines.length}
        itemSize={rowHeight}
        overscanCount={5}
        data-testid="virtual-machine-list"
        width="100%"
      >
        {Row}
      </List>
    )
  }, [loadMore, hasMore, isItemLoaded, itemCount, loadMoreItems, height, rowHeight, Row, machines.length])

  return (
    <div
      style={{
        ...tableStyles.tableContainer
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
          borderBottom: '1px solid var(--color-border-secondary)'
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
      <div data-testid="virtual-machine-keyboard-navigation">
        {content}
      </div>
    </div>
  )
}