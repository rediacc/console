import React, { useState, useEffect } from 'react'
import { Modal, Select, Space, Typography, Spin, Alert, Table, Tag, Empty, Button, Tabs } from 'antd'
import { CloudServerOutlined, CopyOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { 
  useGetAvailableMachinesForClone,
  useGetCloneMachines,
  useUpdateCloneMachineAssignments,
  useUpdateCloneMachineRemovals,
  type DistributedStorageRbdClone
} from '@/api/queries/distributedStorage'
import { showMessage } from '@/utils/messages'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, createModalStyle } from '@/utils/styleConstants'

const { Text } = Typography

interface AssignMachinesToCloneModalProps {
  open: boolean
  clone: DistributedStorageRbdClone | null
  poolName: string
  imageName: string
  snapshotName: string
  teamName: string
  onCancel: () => void
  onSuccess?: () => void
}

export const AssignMachinesToCloneModal: React.FC<AssignMachinesToCloneModalProps> = ({
  open,
  clone,
  poolName,
  imageName,
  snapshotName,
  teamName,
  onCancel,
  onSuccess
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines', 'common'])
  const styles = useComponentStyles()
  const [selectedMachines, setSelectedMachines] = useState<string[]>([])
  const [removingMachines, setRemovingMachines] = useState<string[]>([])
  const [activeTab, setActiveTab] = useState<'assign' | 'manage'>('assign')
  
  // Fetch available machines
  const { data: availableMachines = [], isLoading: loadingAvailable } = useGetAvailableMachinesForClone(
    teamName,
    open && !!clone
  )
  
  // Fetch currently assigned machines
  const { data: assignedMachines = [], isLoading: loadingAssigned, refetch: refetchAssigned } = useGetCloneMachines(
    clone?.cloneName || '',
    snapshotName,
    imageName,
    poolName,
    teamName,
    open && !!clone
  )
  
  // Mutations
  const assignMutation = useUpdateCloneMachineAssignments()
  const removeMutation = useUpdateCloneMachineRemovals()
  
  // Reset state when modal opens/closes
  useEffect(() => {
    if (open) {
      setSelectedMachines([])
      setRemovingMachines([])
      setActiveTab('assign')
    }
  }, [open])
  
  const handleAssign = async () => {
    if (!clone || selectedMachines.length === 0) return
    
    try {
      await assignMutation.mutateAsync({
        teamName,
        poolName,
        imageName,
        snapshotName,
        cloneName: clone.cloneName,
        machineNames: selectedMachines.join(',')
      })
      
      showMessage('success', t('distributedStorage:clones.machinesAssignedSuccess'))
      refetchAssigned()
      setSelectedMachines([])
      onSuccess?.()
    } catch (error) {
      // Error is handled by the mutation
    }
  }
  
  const handleRemove = async () => {
    if (!clone || removingMachines.length === 0) return
    
    try {
      await removeMutation.mutateAsync({
        teamName,
        poolName,
        imageName,
        snapshotName,
        cloneName: clone.cloneName,
        machineNames: removingMachines.join(',')
      })
      
      showMessage('success', t('distributedStorage:clones.machinesRemovedSuccess'))
      refetchAssigned()
      setRemovingMachines([])
      onSuccess?.()
    } catch (error) {
      // Error is handled by the mutation
    }
  }
  
  const renderAssignTab = () => {
    if (loadingAvailable) return <Spin />
    
    if (availableMachines.length === 0) {
      return (
        <Empty
          description={t('machines:noAvailableMachinesForClone')}
          style={{ marginTop: spacing('XL') }}
        />
      )
    }
    
    return (
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert
          message={t('distributedStorage:clones.assignMachinesInfo')}
          type="info"
          showIcon
        />
        
        <div>
          <Text strong style={{ display: 'block', marginBottom: spacing('XS') }}>
            {t('distributedStorage:machines.selectMachines')}:
          </Text>
          <Select
            mode="multiple"
            style={{ width: '100%' }}
            placeholder={t('machines:selectMachines')}
            value={selectedMachines}
            onChange={setSelectedMachines}
            showSearch
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
            options={availableMachines.map(machine => ({
              label: machine.machineName,
              value: machine.machineName
            }))}
            data-testid="assign-clone-machine-select"
          />
          <Text type="secondary" style={{ display: 'block', marginTop: spacing('XS') }} data-testid="assign-clone-selected-count">
            {t('machines:bulkOperations.selectedCount', { count: selectedMachines.length })}
          </Text>
        </div>
      </Space>
    )
  }
  
  const renderManageTab = () => {
    if (loadingAssigned) return <Spin />
    
    if (assignedMachines.length === 0) {
      return (
        <Empty
          description={t('distributedStorage:clones.noMachinesAssigned')}
          style={{ marginTop: spacing('XL') }}
        />
      )
    }
    
    const columns = [
      {
        title: t('machines:machineName'),
        dataIndex: 'machineName',
        key: 'machineName',
        render: (name: string) => (
          <Space>
            <CloudServerOutlined />
            <Text>{name}</Text>
          </Space>
        )
      },
      {
        title: t('machines:bridge'),
        dataIndex: 'bridgeName',
        key: 'bridgeName',
        render: (bridge: string) => <Tag color="green">{bridge}</Tag>
      }
    ]
    
    return (
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert
          message={t('distributedStorage:clones.removeMachinesInfo')}
          type="warning"
          showIcon
        />
        
        <Table
          rowSelection={{
            selectedRowKeys: removingMachines,
            onChange: (keys) => setRemovingMachines(keys as string[]),
            getCheckboxProps: (record) => ({
              'data-testid': `assign-clone-machine-checkbox-${record.machineName}`
            })
          }}
          columns={columns}
          dataSource={assignedMachines}
          rowKey="machineName"
          size="small"
          pagination={false}
          scroll={{ y: 300 }}
          data-testid="assign-clone-machines-table"
        />
        
        <Text type="secondary" data-testid="assign-clone-remove-selected-count">
          {t('machines:bulkOperations.selectedCount', { count: removingMachines.length })}
        </Text>
      </Space>
    )
  }
  
  return (
    <Modal
      data-testid="assign-clone-modal"
      title={
        <Space>
          <CopyOutlined />
          {t('distributedStorage:clones.manageMachines')}
          {clone && (
            <Tag color="orange">{clone.cloneName}</Tag>
          )}
        </Space>
      }
      open={open}
      onCancel={onCancel}
      style={createModalStyle(DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_LG)}
      footer={
        activeTab === 'assign' ? [
          <Button 
            key="cancel" 
            onClick={onCancel} 
            data-testid="assign-clone-cancel"
            style={styles.buttonSecondary}
          >
            {t('common:actions.cancel')}
          </Button>,
          <Button
            key="assign"
            type="primary"
            loading={assignMutation.isPending}
            disabled={selectedMachines.length === 0}
            onClick={handleAssign}
            data-testid="assign-clone-submit"
            style={styles.buttonPrimary}
          >
            {t('distributedStorage:machines.assignMachine')}
          </Button>
        ] : [
          <Button 
            key="cancel" 
            onClick={onCancel} 
            data-testid="assign-clone-cancel"
            style={styles.buttonSecondary}
          >
            {t('common:actions.cancel')}
          </Button>,
          <Button
            key="remove"
            type="primary"
            danger
            loading={removeMutation.isPending}
            disabled={removingMachines.length === 0}
            onClick={handleRemove}
            data-testid="assign-clone-remove-submit"
            style={styles.buttonPrimary}
          >
            {t('distributedStorage:machines.unassignMachine')}
          </Button>
        ]
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as 'assign' | 'manage')}
        data-testid="assign-clone-tabs"
        items={[
          {
            key: 'assign',
            label: t('distributedStorage:clones.assignMachines'),
            children: renderAssignTab()
          },
          {
            key: 'manage',
            label: t('distributedStorage:clones.assignedMachines'),
            children: renderManageTab()
          }
        ]}
      />
    </Modal>
  )
}