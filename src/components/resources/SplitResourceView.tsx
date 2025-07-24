import React, { useState } from 'react'
import { Machine, Repository } from '@/types'
import { MachineTable } from './MachineTable'
import { UnifiedDetailPanel } from './UnifiedDetailPanel'

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
  selectedResource: Machine | Repository | null
  onResourceSelect: (resource: Machine | Repository | null) => void
  onMachineRepositoryClick?: (machine: Machine, repository: any) => void
}

export const SplitResourceView: React.FC<SplitResourceViewProps> = (props) => {
  const { type, selectedResource, onResourceSelect, onMachineRepositoryClick } = props
  const [splitWidth, setSplitWidth] = useState(520) // fixed width for detail panel

  const handleMachineSelect = (machine: Machine) => {
    onResourceSelect(machine)
  }

  const handlePanelClose = () => {
    onResourceSelect(null)
  }

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
      >
        {/* Left Panel - Machine Table */}
        <div 
          style={{
            flex: 1,
            height: '100%',
            overflow: 'hidden',
            minWidth: 0, // Allow flex shrinking
          }}
        >
          <MachineTable
            {...props}
            onRowClick={handleMachineSelect}
            selectedMachine={selectedResource as Machine}
            onMachineRepositoryClick={onMachineRepositoryClick}
          />
        </div>

        {/* Right Panel - Detail Panel */}
        {selectedResource && (
          <UnifiedDetailPanel
            type={'machineName' in selectedResource ? 'machine' : 'repository'}
            data={selectedResource}
            visible={true}
            onClose={handlePanelClose}
            splitWidth={splitWidth}
            onSplitWidthChange={setSplitWidth}
          />
        )}
      </div>
    )
  }

  // For repository type, we'll implement this in SplitRepositoryView
  return null
}