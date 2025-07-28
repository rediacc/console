import React, { useState } from 'react'
import { Modal, Typography, Space, Alert, Table, Tag } from 'antd'
import { CloudServerOutlined, WarningOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Machine } from '@/types'
import { useUpdateMachineClusterAssignment } from '@/api/queries/distributedStorage'
import { showMessage } from '@/utils/messages'

const { Text } = Typography

interface RemoveFromClusterModalProps {
  open: boolean
  machines: Machine[]
  onCancel: () => void
  onSuccess?: () => void
}

export const RemoveFromClusterModal: React.FC<RemoveFromClusterModalProps> = ({
  open,
  machines,
  onCancel,
  onSuccess
}) => {
  const { t } = useTranslation(['machines', 'distributedStorage', 'common'])
  const [removing, setRemoving] = useState(false)
  
  // Update mutation
  const updateMutation = useUpdateMachineClusterAssignment()
  
  // Filter machines that have cluster assignments
  const machinesWithClusters = machines && Array.isArray(machines) 
    ? machines.filter(m => m.distributedStorageClusterName)
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
        disabled: machinesWithClusters.length === 0 
      }}
      width={600}
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
            style={{ marginBottom: 16 }}
          />
          
          <Table
            columns={columns}
            dataSource={machinesWithClusters}
            rowKey="machineName"
            size="small"
            pagination={false}
            scroll={{ y: 300 }}
          />
        </>
      )}
    </Modal>
  )
}