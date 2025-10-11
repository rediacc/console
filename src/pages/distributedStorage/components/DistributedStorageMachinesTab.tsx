import React, { useState } from 'react'
import { 
  Space, 
  Select, 
  Input, 
  Button, 
  Card,
  Row,
  Col
} from 'antd'
import {
  SearchOutlined,
  FilterOutlined,
  ExportOutlined,
  CloudServerOutlined,
  InfoCircleOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { FilterableMachineTable } from './FilterableMachineTable'
import { MachineAvailabilitySummary } from './MachineAvailabilitySummary'
import { useMachines } from '@/api/queries/machines'
import { Machine } from '@/types'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import { AssignToClusterModal } from '@/components/resources/AssignToClusterModal'
import { RemoveFromClusterModal } from '@/components/resources/RemoveFromClusterModal'
import { ViewAssignmentStatusModal } from '@/components/resources/ViewAssignmentStatusModal'
import { showMessage } from '@/utils/messages'

const { Search } = Input

interface DistributedStorageMachinesTabProps {
  teamFilter?: string | string[]
}

type AssignmentFilter = 'all' | 'available' | 'cluster' | 'image' | 'clone'

export const DistributedStorageMachinesTab: React.FC<DistributedStorageMachinesTabProps> = ({
  teamFilter
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines', 'common'])
  const componentStyles = useComponentStyles()
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const isExpertMode = uiMode === 'expert'
  
  // State
  const [searchText, setSearchText] = useState('')
  const [assignmentFilter, setAssignmentFilter] = useState<AssignmentFilter>('all')
  const [selectedMachines, setSelectedMachines] = useState<string[]>([])
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [refreshKeys, setRefreshKeys] = useState<Record<string, number>>({})
  
  // Modal states
  const [assignClusterModal, setAssignClusterModal] = useState<{
    open: boolean
    machine: Machine | null
  }>({ open: false, machine: null })
  
  const [bulkAssignClusterModal, setBulkAssignClusterModal] = useState(false)
  const [removeFromClusterModal, setRemoveFromClusterModal] = useState(false)
  const [viewAssignmentStatusModal, setViewAssignmentStatusModal] = useState(false)
  
  // Queries
  const { data: allMachines = [], isLoading, refetch } = useMachines(teamFilter)
  
  // Filter machines based on search and assignment status
  const filteredMachines = React.useMemo(() => {
    // Ensure allMachines is always an array
    if (!allMachines || !Array.isArray(allMachines)) {
      return []
    }
    
    let filtered = allMachines
    
    // Apply search filter
    if (searchText) {
      filtered = filtered.filter((machine: Machine) => 
        machine.machineName.toLowerCase().includes(searchText.toLowerCase()) ||
        machine.teamName.toLowerCase().includes(searchText.toLowerCase()) ||
        machine.bridgeName.toLowerCase().includes(searchText.toLowerCase())
      )
    }
    
    // Apply assignment filter
    if (assignmentFilter !== 'all') {
      filtered = filtered.filter((machine: Machine) => {
        switch (assignmentFilter) {
          case 'available':
            return !machine.distributedStorageClusterName // TODO: Check image and clone assignments
          case 'cluster':
            return !!machine.distributedStorageClusterName
          case 'image':
            return false // TODO: Implement image assignment check
          case 'clone':
            return false // TODO: Implement clone assignment check
          default:
            return true
        }
      })
    }
    
    return filtered
  }, [allMachines, searchText, assignmentFilter])

  // Handlers
  const handleRefresh = () => {
    refetch()
    setRefreshKeys({})
  }
  
  const handleExport = () => {
    const csvContent = [
      ['Machine Name', 'Team', 'Bridge', 'Assignment Status', 'Assigned To'],
      ...filteredMachines.map((machine: Machine) => [
        machine.machineName,
        machine.teamName,
        machine.bridgeName,
        machine.distributedStorageClusterName ? 'Cluster' : 'Available',
        machine.distributedStorageClusterName || ''
      ])
    ].map(row => row.join(',')).join('\n')
    
    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `distributed-storage-machines-${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    
    showMessage('success', t('common:export.success'))
  }

  // Render bulk actions toolbar
  const renderBulkActionsToolbar = () => {
    if (!isExpertMode || selectedMachines.length === 0) return null
    
    return (
      <div style={{ 
        ...componentStyles.marginBottom.md,
        ...componentStyles.padding.md,
        background: 'var(--color-fill-quaternary)',
        borderRadius: '8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <Space>
          <span style={{ ...componentStyles.label, fontWeight: 500 }}>
            {t('machines:bulkActions.selected', { count: selectedMachines.length })}
          </span>
          <Button
            size="small"
            onClick={() => setSelectedMachines([])}
            data-testid="ds-machines-clear-selection"
            style={componentStyles.touchTarget}
          >
            {t('common:actions.clearSelection')}
          </Button>
        </Space>
        <Space>
          <Button
            type="primary"
            icon={<CloudServerOutlined />}
            onClick={() => setBulkAssignClusterModal(true)}
            data-testid="ds-machines-bulk-assign-cluster"
            style={componentStyles.touchTarget}
          >
            {t('machines:bulkActions.assignToCluster')}
          </Button>
          <Button
            icon={<CloudServerOutlined />}
            onClick={() => setRemoveFromClusterModal(true)}
            data-testid="ds-machines-bulk-remove-cluster"
            style={componentStyles.touchTarget}
          >
            {t('machines:bulkActions.removeFromCluster')}
          </Button>
          <Button
            icon={<InfoCircleOutlined />}
            onClick={() => setViewAssignmentStatusModal(true)}
            data-testid="ds-machines-bulk-view-status"
            style={componentStyles.touchTarget}
          >
            {t('machines:bulkActions.viewAssignmentStatus')}
          </Button>
        </Space>
      </div>
    )
  }
  
  return (
    <>
      {/* Summary Statistics */}
      <MachineAvailabilitySummary 
        teamFilter={teamFilter}
        onRefresh={handleRefresh}
      />
      
      {/* Filters and Actions */}
      <Card style={{ ...componentStyles.card, ...componentStyles.marginBottom.md }}>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={12} lg={8}>
            <Search
              placeholder={t('machines.filters.searchPlaceholder')}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              prefix={<SearchOutlined />}
              allowClear
              data-testid="ds-machines-search"
              style={componentStyles.input}
            />
          </Col>
          
          <Col xs={24} sm={12} lg={8}>
            <Select
              style={{ width: '100%', ...componentStyles.input }}
              placeholder={t('machines.filters.assignmentStatus')}
              value={assignmentFilter}
              onChange={setAssignmentFilter}
              suffixIcon={<FilterOutlined />}
              data-testid="ds-machines-filter-assignment"
            >
              <Select.Option value="all">{t('machines.filters.allStatuses')}</Select.Option>
              <Select.Option value="available">{t('assignment.available')}</Select.Option>
              <Select.Option value="cluster">{t('assignment.assignedToCluster')}</Select.Option>
              <Select.Option value="image">{t('assignment.assignedToImage')}</Select.Option>
              <Select.Option value="clone">{t('assignment.assignedToClone')}</Select.Option>
            </Select>
          </Col>
          
          <Col xs={24} lg={8} style={{ textAlign: 'right' }}>
            <Space>
              <Button
                icon={<ExportOutlined />}
                onClick={handleExport}
                data-testid="ds-machines-export-button"
                style={componentStyles.touchTarget}
              >
                {t('machines.actions.exportReport')}
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>
      
      {/* Bulk Actions Toolbar */}
      {renderBulkActionsToolbar()}
      
      {/* Machine Table */}
      <Card style={componentStyles.card}>
        <FilterableMachineTable
          machines={filteredMachines}
          loading={isLoading}
          selectedRowKeys={selectedMachines}
          onSelectionChange={setSelectedMachines}
          showSelection={isExpertMode}
          expandedRowKeys={expandedRowKeys}
          onExpandedRowsChange={setExpandedRowKeys}
          refreshKeys={refreshKeys}
        />
      </Card>
      
      {/* Modals */}
      <AssignToClusterModal
        open={assignClusterModal.open || bulkAssignClusterModal}
        onCancel={() => {
          setAssignClusterModal({ open: false, machine: null })
          setBulkAssignClusterModal(false)
        }}
        machine={assignClusterModal.machine}
        machines={bulkAssignClusterModal && allMachines && Array.isArray(allMachines) ? 
          allMachines.filter(m => selectedMachines.includes(m.machineName)) : 
          undefined
        }
        onSuccess={() => {
          setAssignClusterModal({ open: false, machine: null })
          setBulkAssignClusterModal(false)
          setSelectedMachines([])
          refetch()
        }}
      />
      
      <RemoveFromClusterModal
        open={removeFromClusterModal}
        onCancel={() => setRemoveFromClusterModal(false)}
        selectedMachines={selectedMachines}
        allMachines={allMachines}
        onSuccess={() => {
          setRemoveFromClusterModal(false)
          setSelectedMachines([])
          refetch()
        }}
      />
      
      <ViewAssignmentStatusModal
        open={viewAssignmentStatusModal}
        onCancel={() => setViewAssignmentStatusModal(false)}
        selectedMachines={selectedMachines}
        allMachines={allMachines}
      />
    </>
  )
}