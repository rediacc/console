import React, { useMemo, useState, useCallback } from 'react'
import { Badge, Select, ButtonProps } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import { Machine, MachineAssignmentType } from '@/types'
import { MachineAssignmentService } from '@/features/distributed-storage'
import { useDebounce } from '@/features/distributed-storage/utils/useDebounce'
import { VirtualMachineTable } from '../VirtualMachineTable'
import {
  Container,
  ToolbarStack,
  FilterControls,
  FilterInput,
  AssignmentSelect,
  PageSizeSelect,
  RefreshButton,
  StatusText,
  OptionLabel,
} from './styles'

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
  teamName: _teamName,
  onRefresh,
  selectable = true,
  onRowClick,
  renderActions,
  height = 600,
}) => {
  const [searchQuery, setSearchQuery] = useState('')
  const [assignmentFilter, setAssignmentFilter] = useState<MachineAssignmentType | 'ALL'>('ALL')
  const [pageSize, setPageSize] = useState(100)
  const [displayedCount, setDisplayedCount] = useState(100)

  const debouncedSearch = useDebounce(searchQuery, 300)

  const filteredMachines = useMemo(() => {
    if (!machines || !Array.isArray(machines)) {
      return []
    }

    let result = machines

    if (assignmentFilter !== 'ALL') {
      result = result.filter((machine) => {
        const assignmentType = MachineAssignmentService.getMachineAssignmentType(machine)
        return assignmentType === assignmentFilter
      })
    }

    if (debouncedSearch) {
      const searchLower = debouncedSearch.toLowerCase()
      result = result.filter(
        (machine) =>
          machine.machineName.toLowerCase().includes(searchLower) ||
          machine.teamName?.toLowerCase().includes(searchLower) ||
          machine.distributedStorageClusterName?.toLowerCase().includes(searchLower),
      )
    }

    return result
  }, [machines, assignmentFilter, debouncedSearch])

  const assignmentCounts = useMemo(() => {
    const counts: Record<MachineAssignmentType | 'ALL', number> = {
      ALL: machines.length,
      AVAILABLE: 0,
      CLUSTER: 0,
      IMAGE: 0,
      CLONE: 0,
    }

    machines.forEach((machine) => {
      const type = MachineAssignmentService.getMachineAssignmentType(machine)
      counts[type] += 1
    })

    return counts
  }, [machines])

  const displayedMachines = useMemo(() => filteredMachines.slice(0, displayedCount), [
    filteredMachines,
    displayedCount,
  ])

  const loadMore = useCallback(async () => {
    await new Promise((resolve) => setTimeout(resolve, 100))
    setDisplayedCount((prev) => Math.min(prev + pageSize, filteredMachines.length))
  }, [pageSize, filteredMachines.length])

  const [prevDebouncedSearch, setPrevDebouncedSearch] = useState(debouncedSearch)
  const [prevAssignmentFilter, setPrevAssignmentFilter] = useState(assignmentFilter)
  const [prevPageSize, setPrevPageSize] = useState(pageSize)

  if (
    debouncedSearch !== prevDebouncedSearch ||
    assignmentFilter !== prevAssignmentFilter ||
    pageSize !== prevPageSize
  ) {
    setPrevDebouncedSearch(debouncedSearch)
    setPrevAssignmentFilter(assignmentFilter)
    setPrevPageSize(pageSize)
    setDisplayedCount(pageSize)
  }

  const hasMore = displayedCount < filteredMachines.length
  const refreshButtonProps: ButtonProps = {
    icon: <ReloadOutlined />,
  }

  return (
    <Container data-testid="filterable-machine-container">
      <ToolbarStack>
        <FilterControls>
          <FilterInput
            data-testid="filterable-machine-search"
            prefix={<SearchOutlined />}
            placeholder="Search machines..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            allowClear
          />

          <AssignmentSelect
            data-testid="filterable-machine-filter-assignment"
            value={assignmentFilter}
            onChange={setAssignmentFilter}
            placeholder="Filter by assignment"
          >
            <Option value="ALL" data-testid="filterable-machine-filter-option-all">
              <Badge count={assignmentCounts.ALL} showZero color="blue">
                <OptionLabel>All Machines</OptionLabel>
              </Badge>
            </Option>
            <Option value="AVAILABLE" data-testid="filterable-machine-filter-option-available">
              <Badge count={assignmentCounts.AVAILABLE} showZero color="green">
                <OptionLabel>Available</OptionLabel>
              </Badge>
            </Option>
            <Option value="CLUSTER" data-testid="filterable-machine-filter-option-cluster">
              <Badge count={assignmentCounts.CLUSTER} showZero color="blue">
                <OptionLabel>Assigned to Cluster</OptionLabel>
              </Badge>
            </Option>
            <Option value="IMAGE" data-testid="filterable-machine-filter-option-image">
              <Badge count={assignmentCounts.IMAGE} showZero color="purple">
                <OptionLabel>Assigned to Image</OptionLabel>
              </Badge>
            </Option>
            <Option value="CLONE" data-testid="filterable-machine-filter-option-clone">
              <Badge count={assignmentCounts.CLONE} showZero color="orange">
                <OptionLabel>Assigned to Clone</OptionLabel>
              </Badge>
            </Option>
          </AssignmentSelect>

          <PageSizeSelect
            data-testid="filterable-machine-page-size"
            value={pageSize}
            onChange={setPageSize}
          >
            <Option value={50} data-testid="filterable-machine-page-size-50">
              50 per batch
            </Option>
            <Option value={100} data-testid="filterable-machine-page-size-100">
              100 per batch
            </Option>
            <Option value={200} data-testid="filterable-machine-page-size-200">
              200 per batch
            </Option>
            <Option value={500} data-testid="filterable-machine-page-size-500">
              500 per batch
            </Option>
          </PageSizeSelect>

          {onRefresh && (
            <RefreshButton
              {...refreshButtonProps}
              data-testid="filterable-machine-refresh"
              onClick={onRefresh}
              loading={loading}
              aria-label="Refresh machines"
            >
              Refresh
            </RefreshButton>
          )}
        </FilterControls>

        <StatusText data-testid="filterable-machine-status">
          Showing {displayedMachines.length} of {filteredMachines.length} machines
          {hasMore && ' (scroll to load more)'}
        </StatusText>
      </ToolbarStack>

      <div data-testid="filterable-machine-table">
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
    </Container>
  )
}
