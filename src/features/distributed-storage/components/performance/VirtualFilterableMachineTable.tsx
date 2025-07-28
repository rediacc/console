import React, { useMemo, useState, useCallback, useRef, useEffect } from 'react'
import { Input, Select, Space, Button, Badge } from 'antd'
import { SearchOutlined, FilterOutlined, ReloadOutlined } from '@ant-design/icons'
import { VirtualMachineTable } from './VirtualMachineTable'
import { Machine, MachineAssignmentType } from '@/types'
import { MachineAssignmentService } from '@/features/distributed-storage'
import { useDebounce } from '@/features/distributed-storage/utils/useDebounce'

const { Option } = Select

interface VirtualFilterableMachineTableProps {
  machines: Machine[]
  loading?: boolean
  teamName?: string
  onRefresh?: () => void
  selectable?: boolean
  onRowClick?: (machine: Machine) => void
  renderActions?: (machine: Machine) => React.ReactNode
  height?: number
}

export const VirtualFilterableMachineTable: React.FC<VirtualFilterableMachineTableProps> = ({
  machines,
  loading = false,
  teamName,
  onRefresh,
  selectable = true,
  onRowClick,
  renderActions,
  height = 600
}) => {
  const [searchQuery, setSearchQuery] = useState('')
  const [assignmentFilter, setAssignmentFilter] = useState<MachineAssignmentType | 'ALL'>('ALL')
  const [pageSize, setPageSize] = useState(100)
  const [displayedCount, setDisplayedCount] = useState(100)
  
  // Use debounced search for better performance
  const debouncedSearch = useDebounce(searchQuery, 300)
  
  // Performance: Memoize filtered machines
  const filteredMachines = useMemo(() => {
    // Ensure machines is always an array
    if (!machines || !Array.isArray(machines)) {
      return []
    }
    
    let result = machines

    // Apply assignment filter
    if (assignmentFilter !== 'ALL') {
      result = result.filter(machine => {
        const assignmentType = MachineAssignmentService.getMachineAssignmentType(machine)
        return assignmentType === assignmentFilter
      })
    }

    // Apply search filter (using debounced value)
    if (debouncedSearch) {
      const searchLower = debouncedSearch.toLowerCase()
      result = result.filter(machine => 
        machine.machineName.toLowerCase().includes(searchLower) ||
        machine.teamName?.toLowerCase().includes(searchLower) ||
        machine.distributedStorageClusterName?.toLowerCase().includes(searchLower)
      )
    }

    return result
  }, [machines, assignmentFilter, debouncedSearch])

  // Get assignment type counts for filter badges
  const assignmentCounts = useMemo(() => {
    const counts: Record<MachineAssignmentType | 'ALL', number> = {
      ALL: machines.length,
      AVAILABLE: 0,
      CLUSTER: 0,
      IMAGE: 0,
      CLONE: 0
    }

    machines.forEach(machine => {
      const type = MachineAssignmentService.getMachineAssignmentType(machine)
      counts[type]++
    })

    return counts
  }, [machines])

  // Virtual scrolling: Only show initially loaded items
  const displayedMachines = useMemo(() => {
    return filteredMachines.slice(0, displayedCount)
  }, [filteredMachines, displayedCount])

  // Load more machines as user scrolls
  const loadMore = useCallback(async () => {
    // Simulate async loading delay
    await new Promise(resolve => setTimeout(resolve, 100))
    
    setDisplayedCount(prev => Math.min(prev + pageSize, filteredMachines.length))
  }, [pageSize, filteredMachines.length])

  // Reset displayed count when filters change
  useEffect(() => {
    setDisplayedCount(pageSize)
  }, [debouncedSearch, assignmentFilter, pageSize])

  const hasMore = displayedCount < filteredMachines.length

  return (
    <div>
      <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
        <Space wrap>
          <Input
            prefix={<SearchOutlined />}
            placeholder="Search machines..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{ width: 300 }}
            allowClear
          />
          
          <Select
            value={assignmentFilter}
            onChange={setAssignmentFilter}
            style={{ width: 200 }}
            placeholder="Filter by assignment"
          >
            <Option value="ALL">
              <Badge count={assignmentCounts.ALL} showZero color="blue">
                <span style={{ paddingRight: 24 }}>All Machines</span>
              </Badge>
            </Option>
            <Option value="AVAILABLE">
              <Badge count={assignmentCounts.AVAILABLE} showZero color="green">
                <span style={{ paddingRight: 24 }}>Available</span>
              </Badge>
            </Option>
            <Option value="CLUSTER">
              <Badge count={assignmentCounts.CLUSTER} showZero color="blue">
                <span style={{ paddingRight: 24 }}>Assigned to Cluster</span>
              </Badge>
            </Option>
            <Option value="IMAGE">
              <Badge count={assignmentCounts.IMAGE} showZero color="purple">
                <span style={{ paddingRight: 24 }}>Assigned to Image</span>
              </Badge>
            </Option>
            <Option value="CLONE">
              <Badge count={assignmentCounts.CLONE} showZero color="orange">
                <span style={{ paddingRight: 24 }}>Assigned to Clone</span>
              </Badge>
            </Option>
          </Select>

          <Select
            value={pageSize}
            onChange={setPageSize}
            style={{ width: 150 }}
          >
            <Option value={50}>50 per batch</Option>
            <Option value={100}>100 per batch</Option>
            <Option value={200}>200 per batch</Option>
            <Option value={500}>500 per batch</Option>
          </Select>

          {onRefresh && (
            <Button
              icon={<ReloadOutlined />}
              onClick={onRefresh}
              loading={loading}
            >
              Refresh
            </Button>
          )}
        </Space>

        <div style={{ color: '#666' }}>
          Showing {displayedMachines.length} of {filteredMachines.length} machines
          {hasMore && ' (scroll to load more)'}
        </div>
      </Space>

      <VirtualMachineTable
        machines={displayedMachines}
        loading={loading}
        hasMore={hasMore}
        loadMore={loadMore}
        height={height}
        selectable={selectable}
        onRowClick={onRowClick}
        renderActions={renderActions}
      />
    </div>
  )
}