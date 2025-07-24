import React, { useState, useRef, useCallback, useEffect } from 'react'
import { Machine } from '@/types'
import { MachineTable } from './MachineTable'
import { MachineVaultStatusPanel } from './MachineVaultStatusPanel'
import { useTheme } from '@/context/ThemeContext'

interface SplitMachineViewProps {
  teamFilter?: string | string[]
  showFilters?: boolean
  showActions?: boolean
  onCreateMachine?: () => void
  onEditMachine?: (machine: Machine) => void
  onVaultMachine?: (machine: Machine) => void
  onFunctionsMachine?: (machine: Machine, functionName?: string) => void
  onDeleteMachine?: (machine: Machine) => void
  onCreateRepository?: (machine: Machine, repositoryGuid?: string) => void
  enabled?: boolean
  className?: string
  expandedRowKeys?: string[]
  onExpandedRowsChange?: (keys: string[]) => void
  refreshKeys?: Record<string, number>
  onQueueItemCreated?: (taskId: string, machineName: string) => void
}

export const SplitMachineView: React.FC<SplitMachineViewProps> = (props) => {
  const { theme } = useTheme()
  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null)
  const [splitWidth, setSplitWidth] = useState(70) // percentage for left panel
  const containerRef = useRef<HTMLDivElement>(null)
  const isDragging = useRef(false)

  const handleMachineSelect = useCallback((machine: Machine) => {
    setSelectedMachine(machine)
  }, [])

  const handlePanelClose = useCallback(() => {
    setSelectedMachine(null)
  }, [])

  const handleMouseDown = useCallback(() => {
    isDragging.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging.current || !containerRef.current) return

    const rect = containerRef.current.getBoundingClientRect()
    const newWidth = ((e.clientX - rect.left) / rect.width) * 100
    
    if (newWidth >= 30 && newWidth <= 85) {
      setSplitWidth(newWidth)
    }
  }, [])

  const handleMouseUp = useCallback(() => {
    isDragging.current = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }, [])

  useEffect(() => {
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [handleMouseMove, handleMouseUp])

  return (
    <div 
      ref={containerRef}
      style={{
        display: 'flex',
        height: '100%',
        width: '100%',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Left Panel - Machine Table */}
      <div 
        style={{
          width: selectedMachine ? `${splitWidth}%` : '100%',
          height: '100%',
          overflow: 'hidden',
          transition: isDragging.current ? 'none' : 'width 0.3s ease',
        }}
      >
        <MachineTable
          {...props}
          onRowClick={handleMachineSelect}
          selectedMachine={selectedMachine}
        />
      </div>

      {/* Resize Handle */}
      {selectedMachine && (
        <>
          <div
            onMouseDown={handleMouseDown}
            style={{
              width: '6px',
              height: '100%',
              backgroundColor: theme === 'dark' ? '#303030' : '#f0f0f0',
              cursor: 'col-resize',
              position: 'relative',
              transition: 'background-color 0.2s',
              '&:hover': {
                backgroundColor: theme === 'dark' ? '#434343' : '#d9d9d9',
              },
            }}
          >
            <div
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                width: '2px',
                height: '30px',
                backgroundColor: theme === 'dark' ? '#595959' : '#bfbfbf',
                borderRadius: '1px',
              }}
            />
          </div>

          {/* Right Panel - Machine Details */}
          <div 
            style={{
              width: `${100 - splitWidth}%`,
              height: '100%',
              overflow: 'hidden',
              backgroundColor: theme === 'dark' ? '#141414' : '#fff',
              borderLeft: `1px solid ${theme === 'dark' ? '#303030' : '#f0f0f0'}`,
            }}
          >
            <MachineVaultStatusPanel
              machine={selectedMachine}
              visible={true}
              onClose={handlePanelClose}
              splitView={true}
            />
          </div>
        </>
      )}
    </div>
  )
}