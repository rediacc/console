import React from 'react'
import { Modal, Table, Space, Tag, Typography } from 'antd'
import { InfoCircleOutlined, CloudServerOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Machine } from '@/types'
import MachineAssignmentStatusBadge from './MachineAssignmentStatusBadge'
import MachineAssignmentStatusCell from './MachineAssignmentStatusCell'

const { Text } = Typography

interface ViewAssignmentStatusModalProps {
  open: boolean
  machines: Machine[]
  onCancel: () => void
}

export const ViewAssignmentStatusModal: React.FC<ViewAssignmentStatusModalProps> = ({
  open,
  machines,
  onCancel
}) => {
  const { t } = useTranslation(['machines', 'distributedStorage', 'common'])
  
  const columns = [
    {
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      width: 200,
      render: (name: string) => (
        <Space>
          <CloudServerOutlined />
          <Text strong>{name}</Text>
        </Space>
      )
    },
    {
      title: t('machines:team'),
      dataIndex: 'teamName',
      key: 'teamName',
      width: 150,
      render: (team: string) => <Tag color="#8FBC8F">{team}</Tag>
    },
    {
      title: t('machines:assignmentStatus.title'),
      key: 'assignmentStatus',
      width: 200,
      render: (_: unknown, record: Machine) => <MachineAssignmentStatusCell machine={record} />
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
  
  // Calculate summary statistics
  const stats = machines.reduce((acc, machine) => {
    if (machine.distributedStorageClusterName) {
      acc.cluster++
    } else {
      acc.available++
    }
    return acc
  }, { available: 0, cluster: 0, image: 0, clone: 0 })
  
  return (
    <Modal
      title={
        <Space>
          <InfoCircleOutlined />
          {t('machines:bulkActions.viewAssignmentStatus')}
        </Space>
      }
      open={open}
      onCancel={onCancel}
      footer={null}
      width={800}
    >
      {/* Summary statistics */}
      <div style={{ marginBottom: 16 }}>
        <Space size="large">
          <div>
            <Text type="secondary">{t('common:total')}: </Text>
            <Text strong>{machines.length}</Text>
          </div>
          <div>
            <MachineAssignmentStatusBadge assignmentType="AVAILABLE" size="small" />
            <Text strong style={{ marginLeft: 8 }}>{stats.available}</Text>
          </div>
          <div>
            <MachineAssignmentStatusBadge assignmentType="CLUSTER" size="small" />
            <Text strong style={{ marginLeft: 8 }}>{stats.cluster}</Text>
          </div>
        </Space>
      </div>
      
      <Table
        columns={columns}
        dataSource={machines}
        rowKey="machineName"
        size="small"
        pagination={{
          pageSize: 10,
          showSizeChanger: false
        }}
        scroll={{ y: 400 }}
      />
    </Modal>
  )
}