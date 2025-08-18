import React, { useState } from 'react'
import { Modal, Typography, Space, Alert, Table, Tag } from 'antd'
import { CloudServerOutlined, WarningOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Machine } from '@/types'
import { useUpdateMachineClusterAssignment } from '@/api/queries/distributedStorage'
import { showMessage } from '@/utils/messages'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, createModalStyle } from '@/utils/styleConstants'

const { Text } = Typography

interface RemoveFromClusterModalProps {
  open: boolean
  selectedMachines?: string[]
  allMachines?: Machine[]
  machines?: Machine[]
  onCancel: () => void
  onSuccess?: () => void
}

export const RemoveFromClusterModal: React.FC<RemoveFromClusterModalProps> = ({
  open,
  machines,
  selectedMachines,
  allMachines,
  onCancel,
  onSuccess
}) => {
  const { t } = useTranslation(['machines', 'distributedStorage', 'common'])
  const styles = useComponentStyles()
  const [removing, setRemoving] = useState(false)
  
  // Update mutation
  const updateMutation = useUpdateMachineClusterAssignment()
  
  // Determine which machines to use
  const targetMachines = machines || (selectedMachines && allMachines 
    ? allMachines.filter(m => selectedMachines.includes(m.machineName))
    : [])
  
  // Filter machines that have cluster assignments
  const machinesWithClusters = targetMachines && Array.isArray(targetMachines) 
    ? targetMachines.filter(m => m.distributedStorageClusterName)
    : []
  
  const handleOk = async () => {
    if (machinesWithClusters.length === 0) return
    
    setRemoving(true)
    
    try {
      // Remove each machine from its cluster
      const results = await Promise.allSettled(
        machinesWithClusters.map(machine => 
          updateMutation.mutateAsync({
            teamName: machine.teamName,
            machineName: machine.machineName,
            clusterName: '' // Empty string to remove assignment
          })
        )
      )
      
      // Count successes and failures
      const succeeded = results.filter(r => r.status === 'fulfilled').length
      const failed = results.filter(r => r.status === 'rejected').length
      
      if (failed === 0) {
        showMessage('success', t('machines:bulkOperations.removalSuccess', { count: succeeded }))
      } else {
        showMessage('warning', t('machines:bulkOperations.assignmentPartial', { 
          success: succeeded, 
          total: machinesWithClusters.length 
        }))
      }
      
      if (onSuccess) onSuccess()
      onCancel()
    } catch (error) {
      showMessage('error', t('distributedStorage:machines.unassignError'))
    } finally {
      setRemoving(false)
    }
  }
  
  const columns = [
    {
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      render: (name: string) => (
        <Space>
          <CloudServerOutlined />
          <Text strong>{name}</Text>
        </Space>
      )
    },
    {
      title: t('distributedStorage:clusters.cluster'),
      dataIndex: 'distributedStorageClusterName',
      key: 'cluster',
      render: (cluster: string) => cluster ? (
        <Tag color="blue">{cluster}</Tag>
      ) : (
        <Text type="secondary">{t('common:none')}</Text>
      )
    }
  ]
  
  return (
    <Modal
      title={
        <Space>
          <WarningOutlined style={{ color: '#ff4d4f' }} />
          {t('machines:bulkActions.removeFromCluster')}
        </Space>
      }
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      okText={t('common:actions.remove')}
      cancelText={t('common:actions.cancel')}
      confirmLoading={removing}
      okButtonProps={{ 
        danger: true,
        disabled: machinesWithClusters.length === 0,
        'data-testid': 'ds-remove-cluster-ok-button',
        style: styles.buttonPrimary
      }}
      cancelButtonProps={{
        'data-testid': 'ds-remove-cluster-cancel-button',
        style: styles.buttonSecondary
      }}
      style={createModalStyle(DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_LG)}
      data-testid="ds-remove-cluster-modal"
    >
      {machinesWithClusters.length === 0 ? (
        <Alert
          message={t('machines:noMachinesWithClusters')}
          type="info"
          showIcon
        />
      ) : (
        <>
          <Alert
            message={t('machines:removeFromClusterWarning', { count: machinesWithClusters.length })}
            description={t('machines:removeFromClusterDescription')}
            type="warning"
            showIcon
            style={{ marginBottom: spacing('MD') }}
          />
          
          <Table
            columns={columns}
            dataSource={machinesWithClusters}
            rowKey="machineName"
            size="small"
            pagination={false}
            scroll={{ y: 300 }}
            data-testid="ds-remove-cluster-table"
          />
        </>
      )}
    </Modal>
  )
}