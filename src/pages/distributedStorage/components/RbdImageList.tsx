import { useState } from 'react'
import { Table, Button, Space, Dropdown, Tag, Tooltip, message } from 'antd'
import { 
  PlusOutlined, 
  SettingOutlined, 
  DeleteOutlined, 
  EllipsisOutlined,
  FileImageOutlined,
  CameraOutlined,
  CopyOutlined,
  ExpandOutlined,
  CloudUploadOutlined,
  CloudDownloadOutlined,
  InfoCircleOutlined,
  CheckCircleOutlined,
  DesktopOutlined,
  SyncOutlined,
  CloudServerOutlined
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import type { MenuProps } from 'antd'
import { 
  useDistributedStorageRbdImages, 
  useDeleteDistributedStorageRbdImage,
  useCreateDistributedStorageRbdImage,
  useUpdateDistributedStoragePoolVault,
  useGetAvailableMachinesForClone,
  type DistributedStorageRbdImage,
  type DistributedStoragePool
} from '@/api/queries/distributedStorage'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { ImageMachineReassignmentModal } from '@/components/resources/ImageMachineReassignmentModal'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import SnapshotList from './SnapshotList'

interface RbdImageListProps {
  pool: DistributedStoragePool
  teamFilter: string | string[]
}

const RbdImageList: React.FC<RbdImageListProps> = ({ pool, teamFilter }) => {
  const { t } = useTranslation('distributedStorage')
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [modalState, setModalState] = useState<{
    open: boolean
    mode: 'create' | 'edit' | 'vault'
    data?: Record<string, any>
  }>({ open: false, mode: 'create' })
  const [queueModalVisible, setQueueModalVisible] = useState(false)
  const [queueModalTaskId, setQueueModalTaskId] = useState<string>('')
  const [reassignMachineModal, setReassignMachineModal] = useState<{
    open: boolean
    image: DistributedStorageRbdImage | null
  }>({ open: false, image: null })
  const managedQueueMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  
  const { data: images = [], isLoading } = useDistributedStorageRbdImages(pool.poolGuid)
  const deleteImageMutation = useDeleteDistributedStorageRbdImage()
  const createImageMutation = useCreateDistributedStorageRbdImage()
  const updateImageVaultMutation = useUpdateDistributedStoragePoolVault()
  
  // Fetch available machines for the team
  const { data: availableMachines = [] } = useGetAvailableMachinesForClone(pool.teamName, modalState.open && modalState.mode === 'create')
  
  const handleCreate = () => {
    setModalState({ open: true, mode: 'create' })
  }
  
  const handleEdit = (image: DistributedStorageRbdImage) => {
    setModalState({ 
      open: true, 
      mode: 'edit', 
      data: {
        ...image,
        vaultContent: image.vaultContent || image.imageVault
      } 
    })
  }
  
  const handleDelete = (image: DistributedStorageRbdImage) => {
    deleteImageMutation.mutate({
      imageName: image.imageName,
      poolName: pool.poolName,
      teamName: image.teamName
    })
  }
  
  const handleReassignMachine = (image: DistributedStorageRbdImage) => {
    setReassignMachineModal({ open: true, image })
  }
  
  const handleRunFunction = async (functionName: string, image?: DistributedStorageRbdImage) => {
    try {
      const queueVault = buildQueueVault({
        function: functionName,
        priority: 3,
        cluster_name: pool.clusterName,
        pool_name: pool.poolName,
        image_name: image?.imageName || '',
      })
      
      const response = await managedQueueMutation.mutateAsync({
        teamName: pool.teamName,
        machineName: pool.clusterName, // Using cluster as machine for distributed storage
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
  
  const getImageMenuItems = (image: DistributedStorageRbdImage): MenuProps['items'] => [
    {
      key: 'edit',
      label: t('images.edit'),
      icon: <SettingOutlined />,
      onClick: () => handleEdit(image),
    },
    {
      key: 'reassignMachine',
      label: t('images.reassignMachine'),
      icon: <CloudServerOutlined />,
      onClick: () => handleReassignMachine(image),
    },
    { type: 'divider' },
    {
      key: 'snapshot',
      label: t('images.createSnapshot'),
      icon: <CameraOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_snapshot_create', image),
    },
    {
      key: 'clone',
      label: t('images.clone'),
      icon: <CopyOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_clone', image),
    },
    {
      key: 'resize',
      label: t('images.resize'),
      icon: <ExpandOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_resize', image),
    },
    { type: 'divider' },
    {
      key: 'export',
      label: t('images.export'),
      icon: <CloudUploadOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_export', image),
    },
    {
      key: 'import',
      label: t('images.import'),
      icon: <CloudDownloadOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_import', image),
    },
    { type: 'divider' },
    {
      key: 'info',
      label: t('images.info'),
      icon: <InfoCircleOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_info', image),
    },
    {
      key: 'status',
      label: t('images.status'),
      icon: <CheckCircleOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_status', image),
    },
    { type: 'divider' },
    {
      key: 'map',
      label: t('images.map'),
      icon: <DesktopOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_map', image),
    },
    {
      key: 'unmap',
      label: t('images.unmap'),
      icon: <DesktopOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_unmap', image),
    },
    {
      key: 'showmapped',
      label: t('images.showMapped'),
      icon: <DesktopOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_showmapped', image),
    },
    { type: 'divider' },
    {
      key: 'flatten',
      label: t('images.flatten'),
      icon: <SyncOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_flatten', image),
    },
    { type: 'divider' },
    {
      key: 'delete',
      label: t('images.delete'),
      icon: <DeleteOutlined />,
      danger: true,
      onClick: () => handleDelete(image),
    },
  ]
  
  const columns = [
    {
      title: t('images.name'),
      dataIndex: 'imageName',
      key: 'imageName',
      render: (text: string, record: DistributedStorageRbdImage) => (
        <Space>
          <FileImageOutlined />
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
      title: t('images.guid'),
      dataIndex: 'imageGuid',
      key: 'imageGuid',
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
      title: t('images.assignedMachine'),
      dataIndex: 'machineName',
      key: 'machineName',
      width: 200,
      render: (machineName: string) => machineName ? (
        <Tag icon={<CloudServerOutlined />} color="blue">
          {machineName}
        </Tag>
      ) : (
        <Tag color="default">
          {t('common.none')}
        </Tag>
      ),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 150,
      render: (_: any, record: DistributedStorageRbdImage) => (
        <Space>
          <Button
            size="small"
            icon={<CloudUploadOutlined />}
            onClick={() => handleRunFunction('distributed_storage_rbd_info', record)}
          >
            {t('common.remote')}
          </Button>
          <Dropdown
            menu={{ items: getImageMenuItems(record) }}
            trigger={['click']}
          >
            <Button size="small" icon={<EllipsisOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ]
  
  const expandedRowRender = (record: DistributedStorageRbdImage) => (
    <SnapshotList 
      image={record} 
      pool={pool}
      teamFilter={teamFilter} 
    />
  )
  
  return (
    <>
      <div style={{ marginBottom: 16 }}>
        <Button 
          type="primary" 
          icon={<PlusOutlined />}
          onClick={handleCreate}
        >
          {t('images.create')}
        </Button>
      </div>
      
      <Table
        columns={columns}
        dataSource={images}
        rowKey="imageGuid"
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
              icon={expanded ? <CameraOutlined /> : <CameraOutlined />}
              onClick={e => onExpand(record, e)}
              style={{ marginRight: 8 }}
            />
          ),
        }}
      />
      
      <UnifiedResourceModal
        open={modalState.open}
        onCancel={() => setModalState({ open: false, mode: 'create' })}
        resourceType="image"
        mode={modalState.mode}
        existingData={{
          ...modalState.data,
          teamName: pool.teamName,
          poolName: pool.poolName,
          pools: [pool],
          availableMachines: availableMachines,
          vaultContent: modalState.data?.vaultContent || modalState.data?.imageVault
        }}
        teamFilter={pool.teamName}
        onSubmit={async (data: any) => {
          if (modalState.mode === 'create') {
            await createImageMutation.mutateAsync({
              poolName: pool.poolName,
              teamName: pool.teamName,
              imageName: data.imageName,
              machineName: data.machineName,
              imageVault: data.imageVault
            })
          } else if (modalState.mode === 'edit') {
            await updateImageVaultMutation.mutateAsync({
              poolName: pool.poolName,
              teamName: pool.teamName,
              imageName: data.imageName,
              imageVault: data.imageVault,
              vaultVersion: modalState.data?.vaultVersion || 0
            })
          }
          setModalState({ open: false, mode: 'create' })
        }}
        isSubmitting={createImageMutation.isPending || updateImageVaultMutation.isPending}
      />
      
      <QueueItemTraceModal
        visible={queueModalVisible}
        onCancel={() => setQueueModalVisible(false)}
        taskId={queueModalTaskId}
      />
      
      <ImageMachineReassignmentModal
        open={reassignMachineModal.open}
        image={reassignMachineModal.image}
        teamName={pool.teamName}
        poolName={pool.poolName}
        onCancel={() => setReassignMachineModal({ open: false, image: null })}
        onSuccess={() => {
          setReassignMachineModal({ open: false, image: null })
          // The query will automatically refresh due to invalidation in the mutation
        }}
      />
    </>
  )
}

export default RbdImageList