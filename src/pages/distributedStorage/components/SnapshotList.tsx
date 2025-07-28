import { useState } from 'react'
import { Table, Button, Space, Dropdown, Tag, Tooltip, message } from 'antd'
import { 
  PlusOutlined, 
  SettingOutlined, 
  DeleteOutlined, 
  EllipsisOutlined,
  CameraOutlined,
  CopyOutlined,
  RollbackOutlined,
  CloudUploadOutlined,
  InfoCircleOutlined,
  SecurityScanOutlined
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import type { MenuProps } from 'antd'
import { 
  useDistributedStorageRbdSnapshots,
  useDeleteDistributedStorageRbdSnapshot,
  useCreateDistributedStorageRbdSnapshot,
  useUpdateDistributedStoragePoolVault,
  type DistributedStorageRbdSnapshot,
  type DistributedStorageRbdImage,
  type DistributedStoragePool
} from '@/api/queries/distributedStorage'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import CloneList from './CloneList'

interface SnapshotListProps {
  image: DistributedStorageRbdImage
  pool: DistributedStoragePool
  teamFilter: string | string[]
}

const SnapshotList: React.FC<SnapshotListProps> = ({ image, pool, teamFilter }) => {
  const { t } = useTranslation('distributedStorage')
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [modalState, setModalState] = useState<{
    open: boolean
    mode: 'create' | 'edit' | 'vault'
    data?: Record<string, any>
  }>({ open: false, mode: 'create' })
  const [queueModalVisible, setQueueModalVisible] = useState(false)
  const [queueModalTaskId, setQueueModalTaskId] = useState<string>('')
  const managedQueueMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  
  const { data: snapshots = [], isLoading } = useDistributedStorageRbdSnapshots(image.imageGuid)
  const deleteSnapshotMutation = useDeleteDistributedStorageRbdSnapshot()
  const createSnapshotMutation = useCreateDistributedStorageRbdSnapshot()
  const updateVaultMutation = useUpdateDistributedStoragePoolVault()
  
  const handleCreate = () => {
    setModalState({ open: true, mode: 'create' })
  }
  
  const handleEdit = (snapshot: DistributedStorageRbdSnapshot) => {
    setModalState({ 
      open: true, 
      mode: 'edit', 
      data: {
        ...snapshot,
        vaultContent: snapshot.vaultContent || snapshot.snapshotVault
      } 
    })
  }
  
  const handleDelete = (snapshot: DistributedStorageRbdSnapshot) => {
    deleteSnapshotMutation.mutate({
      snapshotName: snapshot.snapshotName,
      imageName: image.imageName,
      poolName: pool.poolName,
      teamName: snapshot.teamName
    })
  }
  
  const handleRunFunction = async (functionName: string, snapshot?: DistributedStorageRbdSnapshot) => {
    try {
      const queueVault = buildQueueVault({
        function: functionName,
        priority: 3,
        cluster_name: pool.clusterName,
        pool_name: pool.poolName,
        image_name: image.imageName,
        snapshot_name: snapshot?.snapshotName || '',
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
  
  const getSnapshotMenuItems = (snapshot: DistributedStorageRbdSnapshot): MenuProps['items'] => [
    {
      key: 'edit',
      label: t('snapshots.edit'),
      icon: <SettingOutlined />,
      onClick: () => handleEdit(snapshot),
    },
    { type: 'divider' },
    {
      key: 'clone',
      label: t('snapshots.createClone'),
      icon: <CopyOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_clone_create', snapshot),
    },
    {
      key: 'rollback',
      label: t('snapshots.rollback'),
      icon: <RollbackOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_snapshot_rollback', snapshot),
    },
    { type: 'divider' },
    {
      key: 'export',
      label: t('snapshots.export'),
      icon: <CloudUploadOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_export', snapshot),
    },
    {
      key: 'diff',
      label: t('snapshots.diff'),
      icon: <InfoCircleOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_diff', snapshot),
    },
    { type: 'divider' },
    {
      key: 'protect',
      label: t('snapshots.protect'),
      icon: <SecurityScanOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_snapshot_protect', snapshot),
    },
    {
      key: 'unprotect',
      label: t('snapshots.unprotect'),
      icon: <SecurityScanOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_snapshot_unprotect', snapshot),
    },
    { type: 'divider' },
    {
      key: 'delete',
      label: t('snapshots.delete'),
      icon: <DeleteOutlined />,
      danger: true,
      onClick: () => handleDelete(snapshot),
    },
  ]
  
  const columns = [
    {
      title: t('snapshots.name'),
      dataIndex: 'snapshotName',
      key: 'snapshotName',
      render: (text: string, record: DistributedStorageRbdSnapshot) => (
        <Space>
          <CameraOutlined />
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
      title: t('snapshots.guid'),
      dataIndex: 'snapshotGuid',
      key: 'snapshotGuid',
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
      title: t('common.actions'),
      key: 'actions',
      width: 150,
      render: (_: any, record: DistributedStorageRbdSnapshot) => (
        <Space>
          <Button
            size="small"
            icon={<CloudUploadOutlined />}
            onClick={() => handleRunFunction('distributed_storage_rbd_snapshot_list', record)}
          >
            {t('common.remote')}
          </Button>
          <Dropdown
            menu={{ items: getSnapshotMenuItems(record) }}
            trigger={['click']}
          >
            <Button size="small" icon={<EllipsisOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ]
  
  const expandedRowRender = (record: DistributedStorageRbdSnapshot) => (
    <CloneList 
      snapshot={record}
      image={image}
      pool={pool}
      teamFilter={teamFilter} 
    />
  )
  
  return (
    <>
      <div style={{ padding: '16px', backgroundColor: '#f5f5f5' }}>
        <h4>{t('snapshots.title')}</h4>
        <div style={{ marginBottom: 16 }}>
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={handleCreate}
            size="small"
          >
            {t('snapshots.create')}
          </Button>
        </div>
        
        <Table
          columns={columns}
          dataSource={snapshots}
          rowKey="snapshotGuid"
          loading={isLoading}
          size="small"
          pagination={false}
          expandable={{
            expandedRowRender,
            expandedRowKeys,
            onExpandedRowsChange: setExpandedRowKeys,
            expandIcon: ({ expanded, onExpand, record }) => (
              <Button
                size="small"
                icon={expanded ? <CopyOutlined /> : <CopyOutlined />}
                onClick={e => onExpand(record, e)}
                style={{ marginRight: 8 }}
              />
            ),
          }}
        />
      </div>
      
      <UnifiedResourceModal
        open={modalState.open}
        onCancel={() => setModalState({ open: false, mode: 'create' })}
        resourceType="snapshot"
        mode={modalState.mode}
        existingData={{
          ...modalState.data,
          teamName: pool.teamName,
          poolName: pool.poolName,
          imageName: image.imageName,
          pools: [pool],
          images: [image],
          vaultContent: modalState.data?.vaultContent || modalState.data?.snapshotVault
        }}
        teamFilter={pool.teamName}
        onSubmit={async (data: any) => {
          if (modalState.mode === 'create') {
            await createSnapshotMutation.mutateAsync({
              imageName: image.imageName,
              poolName: pool.poolName,
              teamName: pool.teamName,
              snapshotName: data.snapshotName,
              snapshotVault: data.snapshotVault
            })
          } else if (modalState.mode === 'edit') {
            await updateVaultMutation.mutateAsync({
              poolName: pool.poolName,
              teamName: pool.teamName,
              poolVault: data.snapshotVault,
              vaultVersion: modalState.data?.vaultVersion || 0
            })
          }
          setModalState({ open: false, mode: 'create' })
        }}
        isSubmitting={createSnapshotMutation.isPending || updateVaultMutation.isPending}
      />
      
      <QueueItemTraceModal
        visible={queueModalVisible}
        onCancel={() => setQueueModalVisible(false)}
        taskId={queueModalTaskId}
      />
    </>
  )
}

export default SnapshotList