import React, { useState } from 'react'
import { Modal, Tabs, Table, Button, Space, Tag, Empty, Spin, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { CloudServerOutlined, DesktopOutlined, PlusOutlined, DeleteOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useTableStyles, useComponentStyles } from '@/hooks/useComponentStyles'
import { 
  useDistributedStorageClusterMachines,
  useGetAvailableMachinesForClone,
  useUpdateMachineClusterAssignment,
  useUpdateMachineClusterRemoval
} from '@/api/queries/distributedStorage'
import { AvailableMachinesSelector } from '@/components/resources/AvailableMachinesSelector'
import { formatTimestampAsIs } from '@/utils/timeUtils'

interface ManageClusterMachinesModalProps {
  open: boolean
  clusterName: string
  teamName: string
  onCancel: () => void
  onSuccess?: () => void
}

export const ManageClusterMachinesModal: React.FC<ManageClusterMachinesModalProps> = ({
  open,
  clusterName,
  teamName,
  onCancel,
  onSuccess
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines', 'common'])
  const [activeTab, setActiveTab] = useState<'assign' | 'manage'>('assign')
  const [selectedMachines, setSelectedMachines] = useState<string[]>([])
  const [selectedRemoveMachines, setSelectedRemoveMachines] = useState<string[]>([])
  const [assigningMachines, setAssigningMachines] = useState(false)
  const [removingMachines, setRemovingMachines] = useState(false)
  
  // Fetch cluster machines
  const { data: clusterMachines = [], isLoading: loadingClusterMachines, refetch: refetchClusterMachines } = 
    useDistributedStorageClusterMachines(clusterName, open)
  
  // Fetch available machines
  const { data: availableMachines = [], isLoading: loadingAvailable } = 
    useGetAvailableMachinesForClone(teamName, open && activeTab === 'assign')
  
  // Mutations
  const assignMachine = useUpdateMachineClusterAssignment()
  const removeMachine = useUpdateMachineClusterRemoval()
  
  // Reset state when modal closes
  React.useEffect(() => {
    if (!open) {
      setActiveTab('assign')
      setSelectedMachines([])
      setSelectedRemoveMachines([])
    }
  }, [open])
  
  const handleAssignMachines = async () => {
    if (selectedMachines.length === 0) {
      message.warning(t('machines:bulkOperations.selectMachines'))
      return
    }
    
    setAssigningMachines(true)
    
    try {
      // Assign each machine to the cluster
      const results = await Promise.allSettled(
        selectedMachines.map(machineName =>
          assignMachine.mutateAsync({
            teamName,
            machineName,
            clusterName
          })
        )
      )
      
      const successCount = results.filter(r => r.status === 'fulfilled').length
      const failedCount = results.filter(r => r.status === 'rejected').length
      
      if (failedCount === 0) {
        message.success(t('machines:bulkOperations.assignmentSuccess', { count: successCount }))
        setSelectedMachines([])
        refetchClusterMachines()
        if (onSuccess) onSuccess()
      } else {
        message.warning(t('machines:bulkOperations.assignmentPartial', { 
          success: successCount, 
          total: results.length 
        }))
        refetchClusterMachines()
      }
    } finally {
      setAssigningMachines(false)
    }
  }
  
  const handleRemoveMachines = async () => {
    if (selectedRemoveMachines.length === 0) {
      message.warning(t('machines:validation.noMachinesSelected'))
      return
    }
    
    Modal.confirm({
      title: t('machines:removeFromCluster'),
      content: t('machines:removeFromClusterWarning', { count: selectedRemoveMachines.length }),
      okText: t('common:actions.remove'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onOk: async () => {
        setRemovingMachines(true)
        
        try {
          const results = await Promise.allSettled(
            selectedRemoveMachines.map(machineName =>
              removeMachine.mutateAsync({
                teamName,
                machineName
              })
            )
          )
          
          const successCount = results.filter(r => r.status === 'fulfilled').length
          
          if (successCount === selectedRemoveMachines.length) {
            message.success(t('machines:bulkOperations.removalSuccess', { count: successCount }))
            setSelectedRemoveMachines([])
            refetchClusterMachines()
            if (onSuccess) onSuccess()
          } else {
            message.warning(t('machines:bulkOperations.assignmentPartial', { 
              success: successCount, 
              total: results.length 
            }))
            refetchClusterMachines()
          }
        } finally {
          setRemovingMachines(false)
        }
      }
    })
  }
  
  // Columns for assigned machines table
  const assignedColumns: ColumnsType<any> = [
    {
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      render: (name: string) => (
        <Space>
          <DesktopOutlined />
          <strong>{name}</strong>
        </Space>
      ),
    },
    {
      title: t('machines:bridge'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (name: string) => <Tag color="green">{name}</Tag>,
    },
    {
      title: t('machines:assignedDate'),
      dataIndex: 'assignedDate',
      key: 'assignedDate',
      render: (date: string) => date ? formatTimestampAsIs(date, 'datetime') : '-',
    },
  ]
  
  const renderAssignTab = () => {
    if (loadingAvailable) {
      return <Spin />
    }
    
    return (
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <p>{t('machines:selectMachines')}</p>
          <AvailableMachinesSelector
            availableMachines={availableMachines}
            selectedMachines={selectedMachines}
            onSelectionChange={setSelectedMachines}
            teamName={teamName}
          />
        </div>
        
        {selectedMachines.length > 0 && (
          <div>
            <Tag color="blue">
              {t('machines:bulkOperations.selectedCount', { count: selectedMachines.length })}
            </Tag>
          </div>
        )}
      </Space>
    )
  }
  
  const renderManageTab = () => {
    if (loadingClusterMachines) {
      return <Spin />
    }
    
    if (clusterMachines.length === 0) {
      return <Empty description={t('clusters.noMachinesAssigned')} />
    }
    
    const rowSelection = {
      selectedRowKeys: selectedRemoveMachines,
      onChange: (selectedRowKeys: React.Key[]) => {
        setSelectedRemoveMachines(selectedRowKeys as string[])
      },
    }
    
    return (
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {selectedRemoveMachines.length > 0 && (
          <div>
            <Tag color="orange">
              {t('machines:bulkOperations.selectedCount', { count: selectedRemoveMachines.length })}
            </Tag>
            <Button
              type="primary"
              danger
              icon={<DeleteOutlined />}
              onClick={handleRemoveMachines}
              loading={removingMachines}
              style={{ marginLeft: 8 }}
              data-testid="ds-manage-machines-remove-button"
            >
              {t('machines:removeFromCluster')}
            </Button>
          </div>
        )}
        
        <Table
          rowSelection={rowSelection}
          columns={assignedColumns}
          dataSource={clusterMachines}
          rowKey="machineName"
          size="small"
          pagination={false}
          data-testid="ds-manage-machines-assigned-table"
        />
      </Space>
    )
  }
  
  return (
    <Modal
      title={
        <Space>
          <CloudServerOutlined />
          {t('clusters.assignedMachines')}: {clusterName}
        </Space>
      }
      open={open}
      onCancel={onCancel}
      width={800}
      data-testid="ds-manage-cluster-machines-modal"
      footer={[
        <Button key="cancel" onClick={onCancel} data-testid="ds-manage-machines-cancel">
          {t('common:actions.cancel')}
        </Button>,
        activeTab === 'assign' && (
          <Button
            key="assign"
            type="primary"
            icon={<PlusOutlined />}
            loading={assigningMachines}
            disabled={selectedMachines.length === 0}
            onClick={handleAssignMachines}
            data-testid="ds-manage-machines-assign-button"
          >
            {t('machines:assignToCluster')}
          </Button>
        )
      ].filter(Boolean)}
    >
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as 'assign' | 'manage')}
        data-testid="ds-manage-machines-tabs"
        items={[
          {
            key: 'assign',
            label: <span data-testid="ds-manage-machines-tab-assign">{t('machines:assignToCluster')}</span>,
            children: renderAssignTab()
          },
          {
            key: 'manage',
            label: <span data-testid="ds-manage-machines-tab-manage">{t('clusters.assignedMachines')}</span>,
            children: renderManageTab()
          }
        ]}
      />
    </Modal>
  )
}