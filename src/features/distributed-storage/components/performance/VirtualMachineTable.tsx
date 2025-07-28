import React, { useCallback, useMemo, useRef, useEffect } from 'react'
import { FixedSizeList as List } from 'react-window'
import InfiniteLoader from 'react-window-infinite-loader'
import { Checkbox, Space, Spin } from 'antd'
import { Machine } from '@/types'
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell'
import { useMachineSelection } from '@/store/distributedStorage/hooks'
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
      style={style} 
      className={styles.row}
      onClick={handleRowClick}
    >
      <Space className={styles.rowContent}>
        {selectable && (
          <Checkbox
            checked={isSelected}
            onClick={handleCheckboxChange}
          />
        )}
        <div className={styles.machineName}>{machine.machineName}</div>
        <div className={styles.teamName}>{machine.teamName}</div>
        <MachineAssignmentStatusCell machine={machine} />
        {renderActions && (
          <div className={styles.actions}>
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
        <div style={style} className={styles.loadingRow}>
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
      return (
        <InfiniteLoader
          isItemLoaded={isItemLoaded}
          itemCount={itemCount}
          loadMoreItems={loadMoreItems}
        >
          {({ onItemsRendered, ref }) => (
            <List
              ref={(list) => {
                ref(list)
                listRef.current = list
              }}
              height={height}
              itemCount={itemCount}
              itemSize={rowHeight}
              onItemsRendered={onItemsRendered}
              overscanCount={5}
            >
              {Row}
            </List>
          )}
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
      >
        {Row}
      </List>
    )
  }, [loadMore, hasMore, isItemLoaded, itemCount, loadMoreItems, height, rowHeight, Row, machines.length])

  return (
    <div 
      className={styles.virtualTable}
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      <div className={styles.header}>
        <Space className={styles.headerContent}>
          {selectable && <div className={styles.checkboxColumn} />}
          <div className={styles.machineName}>Machine Name</div>
          <div className={styles.teamName}>Team</div>
          <div className={styles.status}>Assignment Status</div>
          {renderActions && <div className={styles.actions}>Actions</div>}
        </Space>
      </div>
      {content}
    </div>
  )
}