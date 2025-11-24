import React, { useEffect, useState } from 'react'
import { Spin, Tabs } from 'antd'
import { CloudServerOutlined, CopyOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import {
  useGetAvailableMachinesForClone,
  useGetCloneMachines,
  type DistributedStorageRbdClone,
  type AvailableMachine,
  type CloneMachine,
} from '@/api/queries/distributedStorage'
import {
  useUpdateCloneMachineAssignments,
  useUpdateCloneMachineRemovals,
} from '@/api/queries/distributedStorageMutations'
import { showMessage } from '@/utils/messages'
import type { ColumnsType } from 'antd/es/table'
import type { TableRowSelection } from 'antd/es/table/interface'
import {
  StyledModal,
  TitleStack,
  CloneTag,
  AssignTabContainer,
  ManageTabContainer,
  InfoAlert,
  WarningAlert,
  FieldGroup,
  FieldLabel,
  StyledSelect,
  EmptyState,
  MachinesTable,
  MachineNameRow,
  MachineNameText,
  BridgeTag,
  SelectionCount,
  FooterButton,
} from './styles'

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
  const [selectedMachines, setSelectedMachines] = useState<string[]>([])
  const [removingMachines, setRemovingMachines] = useState<string[]>([])
  const [activeTab, setActiveTab] = useState<'assign' | 'manage'>('assign')
  
  // Fetch available machines
  const { data: availableMachines = [], isLoading: loadingAvailable } = useGetAvailableMachinesForClone(
    teamName,
    open && !!clone
  ) as { data?: AvailableMachine[]; isLoading: boolean }
  
  // Fetch currently assigned machines
  const { data: assignedMachines = [], isLoading: loadingAssigned, refetch: refetchAssigned } = useGetCloneMachines(
    clone?.cloneName || '',
    snapshotName,
    imageName,
    poolName,
    teamName,
    open && !!clone
  ) as { data?: CloneMachine[]; isLoading: boolean; refetch: () => Promise<unknown> }
  
  // Mutations
  const assignMutation = useUpdateCloneMachineAssignments()
  const removeMutation = useUpdateCloneMachineRemovals()
  
  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
    } catch {
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
    } catch {
      // Error is handled by the mutation
    }
  }
  
  const renderAssignTab = () => {
    if (loadingAvailable) return <Spin size="small" />
    
    if (availableMachines.length === 0) {
      return <EmptyState description={t('machines:noAvailableMachinesForClone')} />
    }
    
    return (
      <AssignTabContainer>
        <InfoAlert
          message={t('distributedStorage:clones.assignMachinesInfo')}
          type="info"
          showIcon
        />
        
        <FieldGroup>
          <FieldLabel>{t('distributedStorage:machines.selectMachines')}:</FieldLabel>
          <StyledSelect
            mode="multiple"
            placeholder={t('machines:selectMachines')}
            value={selectedMachines}
            onChange={(value) => setSelectedMachines(value as string[])}
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
          <SelectionCount data-testid="assign-clone-selected-count">
            {t('machines:bulkOperations.selectedCount', { count: selectedMachines.length })}
          </SelectionCount>
        </FieldGroup>
      </AssignTabContainer>
    )
  }
  
  const renderManageTab = () => {
    if (loadingAssigned) return <Spin size="small" />
    
    if (assignedMachines.length === 0) {
      return <EmptyState description={t('distributedStorage:clones.noMachinesAssigned')} />
    }
    
    const columns: ColumnsType<CloneMachine> = [
      {
        title: t('machines:machineName'),
        dataIndex: 'machineName',
        key: 'machineName',
        render: (name: string) => (
          <MachineNameRow>
            <CloudServerOutlined />
            <MachineNameText>{name}</MachineNameText>
          </MachineNameRow>
        ),
      },
      {
        title: t('machines:bridge'),
        dataIndex: 'bridgeName',
        key: 'bridgeName',
        render: (bridge: string) => <BridgeTag>{bridge}</BridgeTag>,
      },
    ]
    const rowSelection: TableRowSelection<CloneMachine> = {
      selectedRowKeys: removingMachines,
      onChange: (keys) => setRemovingMachines(keys as string[]),
      getCheckboxProps: (record) =>
        ({
          'data-testid': `assign-clone-machine-checkbox-${record.machineName}`,
        }) as Record<string, unknown>,
    }
    
    return (
      <ManageTabContainer>
        <WarningAlert
          message={t('distributedStorage:clones.removeMachinesInfo')}
          type="warning"
          showIcon
        />
        
        <MachinesTable
          rowSelection={rowSelection}
          columns={columns}
          dataSource={assignedMachines}
          rowKey="machineName"
          size="small"
          pagination={false}
          scroll={{ y: 300 }}
          data-testid="assign-clone-machines-table"
        />
        
        <SelectionCount data-testid="assign-clone-remove-selected-count">
          {t('machines:bulkOperations.selectedCount', { count: removingMachines.length })}
        </SelectionCount>
      </ManageTabContainer>
    )
  }

  const footerButtons =
    activeTab === 'assign'
      ? [
          <FooterButton key="cancel" onClick={onCancel} data-testid="assign-clone-cancel">
            {t('common:actions.cancel')}
          </FooterButton>,
          <FooterButton
            key='assign'
            type="primary"
            loading={assignMutation.isPending}
            disabled={selectedMachines.length === 0}
            onClick={handleAssign}
            data-testid="assign-clone-submit"
          >
            {t('distributedStorage:machines.assignMachine')}
          </FooterButton>,
        ]
      : [
          <FooterButton key="cancel" onClick={onCancel} data-testid="assign-clone-cancel">
            {t('common:actions.cancel')}
          </FooterButton>,
          <FooterButton
            key="remove"
            type="primary"
            danger
            loading={removeMutation.isPending}
            disabled={removingMachines.length === 0}
            onClick={handleRemove}
            data-testid="assign-clone-remove-submit"
          >
            {t('distributedStorage:machines.unassignMachine')}
          </FooterButton>,
        ]

  return (
    <StyledModal
      data-testid="assign-clone-modal"
      title={
        <TitleStack>
          <CopyOutlined />
          {t('distributedStorage:clones.manageMachines')}
          {clone && <CloneTag>{clone.cloneName}</CloneTag>}
        </TitleStack>
      }
      open={open}
      onCancel={onCancel}
      footer={footerButtons}
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
    </StyledModal>
  )
}
