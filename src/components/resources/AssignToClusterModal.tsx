import React, { useState } from 'react'
import { Modal, Select, Space, Typography, Spin, Alert, Table, Tag } from 'antd'
import { CloudServerOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Machine } from '@/types'
import { useDistributedStorageClusters, useUpdateMachineDistributedStorage, useUpdateMachineClusterAssignment } from '@/api/queries/distributedStorage'
import { showMessage } from '@/utils/messages'

const { Text } = Typography

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
  const targetMachines = isBulkMode && machines ? machines : (machine ? [machine] : [])
  
  const [selectedCluster, setSelectedCluster] = useState<string | null>(
    machine?.distributedStorageClusterName || null
  )
  
  // Get unique teams from all machines for bulk mode
  const uniqueTeams = isBulkMode && machines
    ? Array.from(new Set(machines.map(m => m.teamName)))
    : machine ? [machine.teamName] : []
  
  // Load clusters for the machine's team(s)
  const { data: clusters = [], isLoading: clustersLoading } = useDistributedStorageClusters(
    uniqueTeams,
    open && uniqueTeams.length > 0
  )
  
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
    } catch (error) {
      // Error is handled by the mutation
    }
  }
  
  // Reset selected cluster when modal opens with different machine
  React.useEffect(() => {
    if (open && machine && !isBulkMode) {
      setSelectedCluster(machine.distributedStorageClusterName || null)
    } else if (open && isBulkMode) {
      setSelectedCluster(null)
    }
  }, [open, machine, isBulkMode])
  
  const renderBulkMachineList = () => {
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
        title: t('machines:team'),
        dataIndex: 'teamName',
        key: 'teamName',
        render: (team: string) => <Tag color="#8FBC8F">{team}</Tag>
      },
      {
        title: t('machines:assignmentStatus.title'),
        key: 'currentCluster',
        render: (_: unknown, record: Machine) => 
          record.distributedStorageClusterName ? (
            <Tag color="blue">{record.distributedStorageClusterName}</Tag>
          ) : (
            <Tag color="green">{t('machines:assignmentStatus.available')}</Tag>
          )
      }
    ]
    
    return (
      <Table
        columns={columns}
        dataSource={targetMachines}
        rowKey="machineName"
        size="small"
        pagination={false}
        scroll={{ y: 200 }}
        data-testid="ds-assign-cluster-bulk-table"
      />
    )
  }
  
  return (
    <Modal
      title={
        <Space>
          <CloudServerOutlined />
          {isBulkMode 
            ? t('machines:bulkActions.assignToCluster')
            : machine?.distributedStorageClusterName 
              ? t('machines:changeClusterAssignment')
              : t('machines:assignToCluster')
          }
        </Space>
      }
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={updateMutation.isPending || updateClusterMutation.isPending}
      okText={t('common:actions.save')}
      cancelText={t('common:actions.cancel')}
      width={isBulkMode ? 700 : 500}
      okButtonProps={{
        disabled: !selectedCluster,
        'data-testid': 'ds-assign-cluster-ok-button'
      }}
      cancelButtonProps={{
        'data-testid': 'ds-assign-cluster-cancel-button'
      }}
      data-testid="ds-assign-cluster-modal"
    >
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {isBulkMode ? (
          <>
            <Alert
              message={t('machines:bulkOperations.selectedCount', { count: targetMachines.length })}
              description={t('machines:bulkAssignDescription')}
              type="info"
              showIcon
            />
            {renderBulkMachineList()}
          </>
        ) : machine && (
          <>
            <div>
              <Text strong>{t('machines:machine')}: </Text>
              <Text>{machine.machineName}</Text>
            </div>
            
            <div>
              <Text strong>{t('machines:team')}: </Text>
              <Text>{machine.teamName}</Text>
            </div>
            
            {machine.distributedStorageClusterName && (
              <Alert
                message={t('machines:currentClusterAssignment', { 
                  cluster: machine.distributedStorageClusterName 
                })}
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}
          </>
        )}
        
        <div>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>
            {t('distributedStorage:clusters.cluster')}:
          </Text>
          {clustersLoading ? (
            <Spin />
          ) : (
            <>
              <Select
                style={{ width: '100%' }}
                placeholder={t('machines:selectCluster')}
                value={selectedCluster}
                onChange={setSelectedCluster}
                showSearch
                optionFilterProp="children"
                data-testid="ds-assign-cluster-select"
              >
                {clusters.map(cluster => (
                  <Select.Option key={cluster.clusterName} value={cluster.clusterName}>
                    {cluster.clusterName}
                  </Select.Option>
                ))}
              </Select>
              {!isBulkMode && (
                <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                  {t('machines:clusterAssignmentHelp')}
                </Text>
              )}
            </>
          )}
        </div>
      </Space>
    </Modal>
  )
}