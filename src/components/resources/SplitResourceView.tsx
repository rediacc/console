import React, { useState, useEffect } from 'react'
import { Machine, Repository } from '@/types'
import { MachineTable } from './MachineTable'
import { UnifiedDetailPanel } from './UnifiedDetailPanel'
import { usePanelWidth } from '@/hooks/usePanelWidth'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

interface ContainerData {
  id: string
  name: string
  image: string
  command: string
  created: string
  status: string
  state: string
  ports: string
  port_mappings?: Array<{
    host?: string
    host_port?: string
    container_port: string
    protocol: string
  }>
  labels: string
  mounts: string
  networks: string
  size: string
  repository: string
  cpu_percent: string
  memory_usage: string
  memory_percent: string
  net_io: string
  block_io: string
  pids: string
}

interface SplitResourceViewProps {
  type: 'machine' | 'repository'
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
  selectedResource: Machine | Repository | ContainerData | null
  onResourceSelect: (resource: Machine | Repository | ContainerData | null) => void
  isPanelCollapsed?: boolean
  onTogglePanelCollapse?: () => void
}

export const SplitResourceView: React.FC<SplitResourceViewProps> = (props) => {
  const {
    type,
    selectedResource,
    onResourceSelect,
    isPanelCollapsed = true,
    onTogglePanelCollapse
  } = props

  // Use shared panel width hook (33% of window, min 300px, max 700px)
  const panelWidth = usePanelWidth()
  const [splitWidth, setSplitWidth] = useState(panelWidth)
  const [backdropVisible, setBackdropVisible] = useState(false)
  const [shouldRenderBackdrop, setShouldRenderBackdrop] = useState(false)

  // Update splitWidth when window resizes (to keep within bounds)
  useEffect(() => {
    setSplitWidth(panelWidth)
  }, [panelWidth])

  // Manage backdrop fade in/out
  useEffect(() => {
    if (selectedResource) {
      // Mount backdrop and trigger fade-in
      setShouldRenderBackdrop(true)
      requestAnimationFrame(() => {
        setBackdropVisible(true)
      })
    } else {
      // Trigger fade-out
      setBackdropVisible(false)
      // Unmount backdrop after fade-out animation completes
      const timer = setTimeout(() => {
        setShouldRenderBackdrop(false)
      }, 250) // Match transition duration
      return () => clearTimeout(timer)
    }
  }, [selectedResource])

  const handleMachineSelect = (machine: Machine) => {
    onResourceSelect(machine)
  }

  const handlePanelClose = () => {
    onResourceSelect(null)
  }

  // Determine the actual width of the panel based on collapsed state
  const COLLAPSED_PANEL_WIDTH = 50 // Width when collapsed, showing only toggle button
  const actualPanelWidth = isPanelCollapsed ? COLLAPSED_PANEL_WIDTH : splitWidth

  // For machine type, render machine table and detail panel
  if (type === 'machine') {
    return (
      <div
        style={{
          display: 'flex',
          height: '100%',
          width: '100%',
          position: 'relative',
          overflow: 'hidden',
        }}
        data-testid="split-resource-view-container"
      >
        {/* Left Panel - Machine Table */}
        <div
          style={{
            width: selectedResource ? `calc(100% - ${actualPanelWidth}px)` : '100%',
            height: '100%',
            overflow: 'auto',
            minWidth: 300, // Minimum width to prevent crushing the table
            transition: 'width 0.3s ease-in-out',
          }}
          data-testid="split-resource-view-left-panel"
        >
          <MachineTable
            {...props}
            onRowClick={handleMachineSelect}
            selectedMachine={selectedResource as Machine}
          />
        </div>

        {/* Backdrop - appears when panel is open, covers full viewport */}
        {shouldRenderBackdrop && (
          <div
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: actualPanelWidth,
              bottom: 0,
              backgroundColor: 'rgba(0, 0, 0, 0.4)',
              opacity: backdropVisible ? 1 : 0,
              transition: 'opacity 250ms ease-in-out, right 0.3s ease-in-out',
              zIndex: DESIGN_TOKENS.Z_INDEX.MODAL,
              pointerEvents: backdropVisible ? 'auto' : 'none',
            }}
            onClick={handlePanelClose}
            data-testid="split-resource-view-backdrop"
          />
        )}

        {/* Right Panel - Detail Panel */}
        {selectedResource && (
          <UnifiedDetailPanel
            type={'machineName' in selectedResource ? 'machine' :
                  'repositoryName' in selectedResource ? 'repository' : 'container'}
            data={selectedResource}
            visible={true}
            onClose={handlePanelClose}
            splitWidth={splitWidth}
            onSplitWidthChange={setSplitWidth}
            isCollapsed={isPanelCollapsed}
            onToggleCollapse={onTogglePanelCollapse}
            collapsedWidth={COLLAPSED_PANEL_WIDTH}
          />
        )}
      </div>
    )
  }

  // For repository type, we'll implement this in SplitRepositoryView
  return null
}
