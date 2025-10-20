import React, { useState, useEffect } from 'react'
import { Machine, Repository } from '@/types'
import { MachineTable } from './MachineTable'
import { UnifiedDetailPanel } from './UnifiedDetailPanel'

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
  onMachineRepositoryClick?: (machine: Machine, repository: any) => void
  onMachineContainerClick?: (machine: Machine, container: ContainerData) => void
  onRefreshMachines?: () => Promise<any>
  isPanelCollapsed?: boolean
  onTogglePanelCollapse?: () => void
}

export const SplitResourceView: React.FC<SplitResourceViewProps> = (props) => {
  const {
    type,
    selectedResource,
    onResourceSelect,
    onMachineRepositoryClick,
    onMachineContainerClick,
    isPanelCollapsed = true,
    onTogglePanelCollapse
  } = props
  
  // Calculate 25% of window width for the panel
  const calculatePanelWidth = () => {
    const windowWidth = window.innerWidth
    const panelWidth = Math.floor(windowWidth * 0.25)
    // Ensure minimum width of 300px and maximum of 600px
    return Math.max(300, Math.min(600, panelWidth))
  }
  
  const [splitWidth, setSplitWidth] = useState(calculatePanelWidth)

  // Update panel width on window resize
  useEffect(() => {
    const handleResize = () => {
      setSplitWidth(calculatePanelWidth())
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

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
            onMachineRepositoryClick={onMachineRepositoryClick}
            onMachineContainerClick={onMachineContainerClick}
          />
        </div>

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