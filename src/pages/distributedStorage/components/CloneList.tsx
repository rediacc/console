import { useState } from 'react'
import { Table, Button, Space, Dropdown, Tag, Tooltip, message, Badge, Empty, Spin, Typography } from 'antd'
import { 
  PlusOutlined, 
  SettingOutlined, 
  DeleteOutlined, 
  EllipsisOutlined,
  CopyOutlined,
  CloudUploadOutlined,
  InfoCircleOutlined,
  SyncOutlined,
  ScissorOutlined,
  TeamOutlined,
  CloudServerOutlined
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import type { MenuProps } from 'antd'
import { 
  useDistributedStorageRbdClones,
  useDeleteDistributedStorageRbdClone,
  useCreateDistributedStorageRbdClone,
  useUpdateDistributedStoragePoolVault,
  useGetCloneMachines,
  type DistributedStorageRbdClone,
  type DistributedStorageRbdSnapshot,
  type DistributedStorageRbdImage,
  type DistributedStoragePool,
  type CloneMachine
} from '@/api/queries/distributedStorage'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { AssignMachinesToCloneModal } from '@/components/resources/AssignMachinesToCloneModal'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'

const { Text } = Typography

interface CloneListProps {
  snapshot: DistributedStorageRbdSnapshot
  image: DistributedStorageRbdImage
  pool: DistributedStoragePool
  teamFilter: string | string[]
}

const CloneList: React.FC<CloneListProps> = ({ snapshot, image, pool, teamFilter }) => {
  const { t } = useTranslation('distributedStorage')
  const [modalState, setModalState] = useState<{
    open: boolean
    mode: 'create' | 'edit' | 'vault'
    data?: Record<string, any>
  }>({ open: false, mode: 'create' })
  const [queueModalVisible, setQueueModalVisible] = useState(false)
  const [queueModalTaskId, setQueueModalTaskId] = useState<string>('')
  const [machineModalState, setMachineModalState] = useState<{
    open: boolean
    clone: DistributedStorageRbdClone | null
  }>({ open: false, clone: null })
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  
  const managedQueueMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  
  const { data: clones = [], isLoading } = useDistributedStorageRbdClones(snapshot.snapshotGuid)
  const deleteCloneMutation = useDeleteDistributedStorageRbdClone()
  const createCloneMutation = useCreateDistributedStorageRbdClone()
  const updateVaultMutation = useUpdateDistributedStoragePoolVault()
  
  const handleCreate = () => {
    setModalState({ open: true, mode: 'create' })
  }
  
  const handleEdit = (clone: DistributedStorageRbdClone) => {
    setModalState({ 
      open: true, 
      mode: 'edit', 
      data: {
        ...clone,
        vaultContent: clone.vaultContent || clone.cloneVault
      } 
    })
  }
  
  const handleDelete = (clone: DistributedStorageRbdClone) => {
    deleteCloneMutation.mutate({
      cloneName: clone.cloneName,
      snapshotName: snapshot.snapshotName,
      imageName: image.imageName,
      poolName: pool.poolName,
      teamName: clone.teamName
    })
  }
  
  const handleRunFunction = async (functionName: string, clone?: DistributedStorageRbdClone) => {
    try {
      const queueVault = buildQueueVault({
        function: functionName,
        priority: 3,
        cluster_name: pool.clusterName,
        pool_name: pool.poolName,
        image_name: image.imageName,
        snapshot_name: snapshot.snapshotName,
        clone_name: clone?.cloneName || '',
      })
      
      const response = await managedQueueMutation.mutateAsync({
        teamName: pool.teamName,
        machineName: pool.clusterName,
        bridgeName: 'default',
        queueVault,
        priority: 3
      })
      
      if (response.taskId) {
        handleQueueItemCreated(response.taskId)
      }
    } catch (error) {
      message.error(t('queue.createError'))
    }
  }
  
  const handleQueueItemCreated = (taskId: string) => {
    setQueueModalTaskId(taskId)
    setQueueModalVisible(true)
    message.success(t('queue.itemCreated'))
  }
  
  const handleManageMachines = (clone: DistributedStorageRbdClone) => {
    setMachineModalState({ open: true, clone })
  }
  
  const getCloneMenuItems = (clone: DistributedStorageRbdClone): MenuProps['items'] => [
    {
      key: 'edit',
      label: t('clones.edit'),
      icon: <SettingOutlined />,
      onClick: () => handleEdit(clone),
    },
    {
      key: 'manageMachines',
      label: t('clones.manageMachines'),
      icon: <TeamOutlined />,
      onClick: () => handleManageMachines(clone),
    },
    { type: 'divider' },
    {
      key: 'flatten',
      label: t('clones.flatten'),
      icon: <SyncOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_flatten', clone),
    },
    {
      key: 'split',
      label: t('clones.split'),
      icon: <ScissorOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_clone_split', clone),
    },
    { type: 'divider' },
    {
      key: 'export',
      label: t('clones.export'),
      icon: <CloudUploadOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_export', clone),
    },
    {
      key: 'info',
      label: t('clones.info'),
      icon: <InfoCircleOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_info', clone),
    },
    { type: 'divider' },
    {
      key: 'delete',
      label: t('clones.delete'),
      icon: <DeleteOutlined />,
      danger: true,
      onClick: () => handleDelete(clone),
    },
  ]
  
  // Component to show assigned machines in expandable row
  const CloneMachineList: React.FC<{
    clone: DistributedStorageRbdClone
    snapshot: DistributedStorageRbdSnapshot
    image: DistributedStorageRbdImage
    pool: DistributedStoragePool
  }> = ({ clone, snapshot, image, pool }) => {
    const { data: machines = [], isLoading } = useGetCloneMachines(
      clone.cloneName,
      snapshot.snapshotName,
      image.imageName,
      pool.poolName,
      pool.teamName,
      true
    )
    
    if (isLoading) return <Spin />
    
    if (machines.length === 0) {
      return (
        <div style={{ padding: '16px', textAlign: 'center' }}>
          <Empty description={t('clones.noMachinesAssigned')} />
          <Button
            type="primary"
            icon={<TeamOutlined />}
            onClick={() => handleManageMachines(clone)}
            style={{ marginTop: 16 }}
          >
            {t('clones.assignMachines')}
          </Button>
        </div>
      )
    }
    
    return (
      <div style={{ padding: '16px' }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space>
            <TeamOutlined />
            <Text strong>{t('clones.assignedMachines')}:</Text>
            <Tag>{machines.length} {t('machines:machines')}</Tag>
          </Space>
          
          <Space wrap>
            {machines.map((machine) => (
              <Tag key={machine.machineName} icon={<CloudServerOutlined />} color="blue">
                {machine.machineName}
              </Tag>
            ))}
          </Space>
          
          <Button
            icon={<TeamOutlined />}
            onClick={() => handleManageMachines(clone)}
          >
            {t('clones.manageMachines')}
          </Button>
        </Space>
      </div>
    )
  }
  
  // Component to show machine count
  const MachineCountBadge: React.FC<{ clone: DistributedStorageRbdClone }> = ({ clone }) => {
    const { data: machines = [] } = useGetCloneMachines(
      clone.cloneName,
      snapshot.snapshotName,
      image.imageName,
      pool.poolName,
      pool.teamName,
      true
    )
    
    return (
      <Badge count={machines.length} showZero style={{ backgroundColor: machines.length > 0 ? '#52c41a' : '#d9d9d9' }}>
        <CloudServerOutlined style={{ fontSize: 16 }} />
      </Badge>
    )
  }
  
  const columns = [
    {
      title: t('clones.name'),
      dataIndex: 'cloneName',
      key: 'cloneName',
      render: (text: string, record: DistributedStorageRbdClone) => (
        <Space>
          <CopyOutlined />
          <span>{text}</span>
          {record.vaultContent && (
            <Tooltip title={t('common.hasVault')}>
              <Tag color="blue">{t('common.vault')}</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: t('clones.guid'),
      dataIndex: 'cloneGuid',
      key: 'cloneGuid',
      width: 300,
      render: (text: string) => (
        <Tooltip title={text}>
          <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>
            {text.substring(0, 8)}...
          </span>
        </Tooltip>
      ),
    },
    {
      title: t('machines:machines'),
      key: 'machines',
      width: 100,
      align: 'center' as const,
      render: (_: any, record: DistributedStorageRbdClone) => <MachineCountBadge clone={record} />
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 150,
      render: (_: any, record: DistributedStorageRbdClone) => (
        <Space>
          <Button
            size="small"
            icon={<CloudUploadOutlined />}
            onClick={() => handleRunFunction('distributed_storage_rbd_info', record)}
          >
            {t('common.remote')}
          </Button>
          <Dropdown
            menu={{ items: getCloneMenuItems(record) }}
            trigger={['click']}
          >
            <Button size="small" icon={<EllipsisOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ]
  
  return (
    <>
      <div style={{ padding: '16px 16px 16px 32px', backgroundColor: '#fafafa' }}>
        <h5>{t('clones.title')}</h5>
        <div style={{ marginBottom: 16 }}>
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={handleCreate}
            size="small"
          >
            {t('clones.create')}
          </Button>
        </div>
        
        <Table
          columns={columns}
          dataSource={clones}
          rowKey="cloneGuid"
          loading={isLoading}
          size="small"
          pagination={false}
          expandable={{
            expandedRowRender: (record) => <CloneMachineList clone={record} snapshot={snapshot} image={image} pool={pool} />,
            rowExpandable: () => true,
            expandedRowKeys,
            onExpandedRowsChange: setExpandedRowKeys,
          }}
        />
      </div>
      
      <UnifiedResourceModal
        open={modalState.open}
        onCancel={() => setModalState({ open: false, mode: 'create' })}
        resourceType="clone"
        mode={modalState.mode}
        existingData={{
          ...modalState.data,
          teamName: pool.teamName,
          poolName: pool.poolName,
          imageName: image.imageName,
          snapshotName: snapshot.snapshotName,
          pools: [pool],
          images: [image],
          snapshots: [snapshot],
          vaultContent: modalState.data?.vaultContent || modalState.data?.cloneVault
        }}
        teamFilter={pool.teamName}
        onSubmit={async (data: any) => {
          if (modalState.mode === 'create') {
            await createCloneMutation.mutateAsync({
              snapshotName: snapshot.snapshotName,
              imageName: image.imageName,
              poolName: pool.poolName,
              teamName: pool.teamName,
              cloneName: data.cloneName,
              cloneVault: data.cloneVault
            })
          } else if (modalState.mode === 'edit') {
            await updateVaultMutation.mutateAsync({
              poolName: pool.poolName,
              teamName: pool.teamName,
              poolVault: data.cloneVault,
              vaultVersion: modalState.data?.vaultVersion || 0
            })
          }
          setModalState({ open: false, mode: 'create' })
        }}
        isSubmitting={createCloneMutation.isPending || updateVaultMutation.isPending}
      />
      
      <QueueItemTraceModal
        visible={queueModalVisible}
        onCancel={() => setQueueModalVisible(false)}
        taskId={queueModalTaskId}
      />
      
      <AssignMachinesToCloneModal
        open={machineModalState.open}
        clone={machineModalState.clone}
        poolName={pool.poolName}
        imageName={image.imageName}
        snapshotName={snapshot.snapshotName}
        teamName={pool.teamName}
        onCancel={() => setMachineModalState({ open: false, clone: null })}
        onSuccess={() => {
          setMachineModalState({ open: false, clone: null })
          // Refresh the clone list to update machine counts
        }}
      />
    </>
  )
}

export default CloneList