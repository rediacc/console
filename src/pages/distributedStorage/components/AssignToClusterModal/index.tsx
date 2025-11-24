import React, { useEffect, useMemo, useState } from 'react'
import { CloudServerOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { Machine } from '@/types'
import {
  useDistributedStorageClusters,
  type DistributedStorageCluster,
} from '@/api/queries/distributedStorage'
import {
  useUpdateMachineDistributedStorage,
  useUpdateMachineClusterAssignment,
} from '@/api/queries/distributedStorageMutations'
import { showMessage } from '@/utils/messages'
import { Select } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ModalSize } from '@/types/modal'
import LoadingWrapper from '@/components/common/LoadingWrapper'
import { createTruncatedColumn } from '@/components/common/columns'
import {
  StyledModal,
  TitleStack,
  ContentStack,
  InfoAlert,
  MachineDetailsSection,
  DetailRow,
  DetailLabel,
  DetailValue,
  ClusterAlert,
  FieldGroup,
  FieldLabel,
  HelperText,
  StyledSelect,
  MachinesTable,
  MachineNameRow,
  MachineNameText,
  TeamTag,
  AssignmentTag,
} from './styles'

interface AssignToClusterModalProps {
  open: boolean
  machine?: Machine | null
  machines?: Machine[]  // For bulk operations
  onCancel: () => void
  onSuccess?: () => void
}

export const AssignToClusterModal: React.FC<AssignToClusterModalProps> = ({
  open,
  machine,
  machines,
  onCancel,
  onSuccess
}) => {
  const { t } = useTranslation(['machines', 'distributedStorage', 'common'])
  const isBulkMode = !!machines && machines.length > 0
  const targetMachines: Machine[] = isBulkMode && machines ? machines : machine ? [machine] : []
  
  const [selectedCluster, setSelectedCluster] = useState<string | null>(
    machine?.distributedStorageClusterName || null
  )
  
  // Get unique teams from all machines for bulk mode
  const uniqueTeams: string[] = isBulkMode && machines
    ? Array.from(new Set(machines.map(m => m.teamName)))
    : machine ? [machine.teamName] : []
  
  // Load clusters for the machine's team(s)
  const { data: clusters = [], isLoading: clustersLoading } = useDistributedStorageClusters(
    uniqueTeams,
    open && uniqueTeams.length > 0
  ) as { data: DistributedStorageCluster[]; isLoading: boolean }
  
  // Update mutations
  const updateMutation = useUpdateMachineDistributedStorage()
  const updateClusterMutation = useUpdateMachineClusterAssignment()
  
  const handleOk = async () => {
    if (!selectedCluster || targetMachines.length === 0) return
    
    try {
      if (isBulkMode) {
        // Bulk assignment
        const results = await Promise.allSettled(
          targetMachines.map(m => 
            updateClusterMutation.mutateAsync({
              teamName: m.teamName,
              machineName: m.machineName,
              clusterName: selectedCluster
            })
          )
        )
        
        const succeeded = results.filter(r => r.status === 'fulfilled').length
        const failed = results.filter(r => r.status === 'rejected').length
        
        if (failed === 0) {
          showMessage('success', t('machines:bulkOperations.assignmentSuccess', { count: succeeded }))
        } else {
          showMessage('warning', t('machines:bulkOperations.assignmentPartial', { 
            success: succeeded, 
            total: targetMachines.length 
          }))
        }
      } else {
        // Single assignment
        await updateMutation.mutateAsync({
          teamName: machine!.teamName,
          machineName: machine!.machineName,
          clusterName: selectedCluster
        })
        
        showMessage(
          'success', 
          selectedCluster 
            ? t('machines:clusterAssignedSuccess', { cluster: selectedCluster })
            : t('machines:clusterUnassignedSuccess')
        )
      }
      
      onSuccess?.()
      onCancel()
    } catch {
      // Error is handled by the mutation
    }
  }
  
  // Reset selected cluster when modal opens with different machine
  useEffect(() => {
    if (open && machine && !isBulkMode) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedCluster(machine.distributedStorageClusterName || null)
    } else if (open && isBulkMode) {
      setSelectedCluster(null)
    }
  }, [open, machine, isBulkMode])

  const bulkColumns: ColumnsType<Machine> = useMemo(() => {
    const machineColumn = createTruncatedColumn<Machine>({
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      renderWrapper: (content) => (
        <MachineNameRow>
          <CloudServerOutlined />
          <MachineNameText>{content}</MachineNameText>
        </MachineNameRow>
      ),
    })

    const teamColumn = createTruncatedColumn<Machine>({
      title: t('machines:team'),
      dataIndex: 'teamName',
      key: 'teamName',
      renderWrapper: (content) => <TeamTag>{content}</TeamTag>,
    })

    return [
      machineColumn,
      teamColumn,
      {
        title: t('machines:assignmentStatus.title'),
        key: 'currentCluster',
        render: (_: unknown, record: Machine) =>
          record.distributedStorageClusterName ? (
            <AssignmentTag $variant="cluster">{record.distributedStorageClusterName}</AssignmentTag>
          ) : (
            <AssignmentTag $variant="available">
              {t('machines:assignmentStatus.available')}
            </AssignmentTag>
          ),
      },
    ]
  }, [t])

  const modalSize = isBulkMode ? ModalSize.Large : ModalSize.Medium
  
  return (
    <StyledModal
      $size={modalSize}
      title={
        <TitleStack>
          <CloudServerOutlined />
          {isBulkMode 
            ? t('machines:bulkActions.assignToCluster')
            : machine?.distributedStorageClusterName 
              ? t('machines:changeClusterAssignment')
              : t('machines:assignToCluster')
          }
        </TitleStack>
      }
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={updateMutation.isPending || updateClusterMutation.isPending}
      okText={t('common:actions.save')}
      cancelText={t('common:actions.cancel')}
      okButtonProps={{
        disabled: !selectedCluster,
        'data-testid': 'ds-assign-cluster-ok-button',
      }}
      cancelButtonProps={{
        'data-testid': 'ds-assign-cluster-cancel-button',
      }}
      data-testid="ds-assign-cluster-modal"
    >
      <ContentStack>
        {isBulkMode ? (
          <>
            <InfoAlert
              message={t('machines:bulkOperations.selectedCount', { count: targetMachines.length })}
              description={t('machines:bulkAssignDescription')}
              type="info"
              showIcon
            />
            <MachinesTable
              columns={bulkColumns}
              dataSource={targetMachines}
              rowKey="machineName"
              size="small"
              pagination={false}
              scroll={{ y: 200 }}
              data-testid="ds-assign-cluster-bulk-table"
            />
          </>
        ) : machine && (
          <>
            <MachineDetailsSection>
              <DetailRow>
                <DetailLabel>{t('machines:machine')}:</DetailLabel>
                <DetailValue>{machine.machineName}</DetailValue>
              </DetailRow>
              <DetailRow>
                <DetailLabel>{t('machines:team')}:</DetailLabel>
                <DetailValue>{machine.teamName}</DetailValue>
              </DetailRow>
            </MachineDetailsSection>
            
            {machine.distributedStorageClusterName && (
              <ClusterAlert
                message={t('machines:currentClusterAssignment', { 
                  cluster: machine.distributedStorageClusterName 
                })}
                type="info"
                showIcon
              />
            )}
          </>
        )}
        
        <FieldGroup>
          <FieldLabel>{t('distributedStorage:clusters.cluster')}:</FieldLabel>
          {clustersLoading ? (
            <LoadingWrapper loading centered minHeight={80}>
              <div />
            </LoadingWrapper>
          ) : (
            <>
              <StyledSelect
                placeholder={t('machines:selectCluster')}
                value={selectedCluster}
                onChange={(value) => setSelectedCluster(value as string | null)}
                showSearch
                optionFilterProp="children"
                data-testid="ds-assign-cluster-select"
              >
                {clusters.map((cluster) => (
                  <Select.Option
                    key={cluster.clusterName}
                    value={cluster.clusterName}
                    data-testid={`cluster-option-${cluster.clusterName}`}
                  >
                    {cluster.clusterName}
                  </Select.Option>
                ))}
              </StyledSelect>
              {!isBulkMode && (
                <HelperText>
                  {t('machines:clusterAssignmentHelp')}
                </HelperText>
              )}
            </>
          )}
        </FieldGroup>
      </ContentStack>
    </StyledModal>
  )
}
