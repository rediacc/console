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
import { useTableStyles, useComponentStyles } from '@/hooks/useComponentStyles'
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
import { createSorter } from '@/utils/tableSorters'

interface RbdImageListProps {
  pool: DistributedStoragePool
  teamFilter: string | string[]
}

const RbdImageList: React.FC<RbdImageListProps> = ({ pool, teamFilter }) => {
  const { t } = useTranslation('distributedStorage')
  const tableStyles = useTableStyles()
  const componentStyles = useComponentStyles()
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
      const queueVault = await buildQueueVault({
        functionName: functionName,
        teamName: pool.teamName,
        machineName: pool.clusterName,
        bridgeName: 'default',
        params: {
          cluster_name: pool.clusterName,
          pool_name: pool.poolName,
          image_name: image?.imageName || '',
        },
        priority: 3,
        description: `Execute ${functionName}`,
        addedVia: 'DistributedStorage'
      })
      
      const response = await managedQueueMutation.mutateAsync({
        teamName: pool.teamName,
        machineName: pool.clusterName, // Using cluster as machine for distributed storage
        bridgeName: 'default',
        queueVault,
        priority: 3
      })

      const taskId = response.taskId
      if (taskId) {
        handleQueueItemCreated(taskId)
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
      label: <span data-testid={`rbd-edit-action-${image.imageName}`}>{t('images.edit')}</span>,
      icon: <SettingOutlined />,
      onClick: () => handleEdit(image),
    },
    {
      key: 'reassignMachine',
      label: <span data-testid={`rbd-reassign-action-${image.imageName}`}>{t('images.reassignMachine')}</span>,
      icon: <CloudServerOutlined />,
      onClick: () => handleReassignMachine(image),
    },
    { type: 'divider' },
    {
      key: 'snapshot',
      label: <span data-testid={`rbd-snapshot-action-${image.imageName}`}>{t('images.createSnapshot')}</span>,
      icon: <CameraOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_snapshot_create', image),
    },
    {
      key: 'clone',
      label: <span data-testid={`rbd-clone-action-${image.imageName}`}>{t('images.clone')}</span>,
      icon: <CopyOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_clone', image),
    },
    {
      key: 'resize',
      label: <span data-testid={`rbd-resize-action-${image.imageName}`}>{t('images.resize')}</span>,
      icon: <ExpandOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_resize', image),
    },
    { type: 'divider' },
    {
      key: 'export',
      label: <span data-testid={`rbd-export-action-${image.imageName}`}>{t('images.export')}</span>,
      icon: <CloudUploadOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_export', image),
    },
    {
      key: 'import',
      label: <span data-testid={`rbd-import-action-${image.imageName}`}>{t('images.import')}</span>,
      icon: <CloudDownloadOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_import', image),
    },
    { type: 'divider' },
    {
      key: 'info',
      label: <span data-testid={`rbd-info-action-${image.imageName}`}>{t('images.info')}</span>,
      icon: <InfoCircleOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_info', image),
    },
    {
      key: 'status',
      label: <span data-testid={`rbd-status-action-${image.imageName}`}>{t('images.status')}</span>,
      icon: <CheckCircleOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_status', image),
    },
    { type: 'divider' },
    {
      key: 'map',
      label: <span data-testid={`rbd-map-action-${image.imageName}`}>{t('images.map')}</span>,
      icon: <DesktopOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_map', image),
    },
    {
      key: 'unmap',
      label: <span data-testid={`rbd-unmap-action-${image.imageName}`}>{t('images.unmap')}</span>,
      icon: <DesktopOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_unmap', image),
    },
    {
      key: 'showmapped',
      label: <span data-testid={`rbd-showmapped-action-${image.imageName}`}>{t('images.showMapped')}</span>,
      icon: <DesktopOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_showmapped', image),
    },
    { type: 'divider' },
    {
      key: 'flatten',
      label: <span data-testid={`rbd-flatten-action-${image.imageName}`}>{t('images.flatten')}</span>,
      icon: <SyncOutlined />,
      onClick: () => handleRunFunction('distributed_storage_rbd_flatten', image),
    },
    { type: 'divider' },
    {
      key: 'delete',
      label: <span data-testid={`rbd-delete-action-${image.imageName}`}>{t('images.delete')}</span>,
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
      sorter: createSorter<DistributedStorageRbdImage>('imageName'),
      render: (text: string, record: DistributedStorageRbdImage) => (
        <Space data-testid={`rbd-image-name-${record.imageName}`}>
          <FileImageOutlined style={{ ...tableStyles.icon.medium, color: 'var(--color-primary)' }} />
          <span style={{ color: 'var(--color-text-primary)' }}>{text}</span>
          {record.vaultContent && (
            <Tooltip title={t('common.hasVault')}>
              <Tag color="blue" data-testid={`rbd-vault-tag-${record.imageName}`}>{t('common.vault')}</Tag>
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
      sorter: createSorter<DistributedStorageRbdImage>('imageGuid'),
      render: (text: string) => (
        <Tooltip title={text}>
          <span style={{ fontFamily: 'monospace', fontSize: '12px', color: 'var(--color-text-secondary)' }}>
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
      sorter: createSorter<DistributedStorageRbdImage>('machineName'),
      render: (machineName: string, record: DistributedStorageRbdImage) => machineName ? (
        <Tag icon={<CloudServerOutlined />} color="blue" data-testid={`rbd-machine-tag-${record.imageName}`}>
          {machineName}
        </Tag>
      ) : (
        <Tag color="default" data-testid={`rbd-machine-none-${record.imageName}`}>
          {t('common.none')}
        </Tag>
      ),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 150,
      render: (_: unknown, record: DistributedStorageRbdImage) => (
        <Space data-testid={`rbd-image-actions-${record.imageName}`}>
          <Tooltip title={t('common.remote')}>
            <Button
              size="small"
              icon={<CloudUploadOutlined />}
              onClick={() => handleRunFunction('distributed_storage_rbd_info', record)}
              data-testid={`rbd-remote-button-${record.imageName}`}
              style={tableStyles.tableActionButton}
              aria-label={t('common.remote')}
            />
          </Tooltip>
          <Dropdown
            menu={{ items: getImageMenuItems(record) }}
            trigger={['click']}
          >
            <Button 
              size="small" 
              icon={<EllipsisOutlined />} 
              data-testid={`rbd-actions-dropdown-${record.imageName}`}
              style={tableStyles.tableActionButton}
            />
          </Dropdown>
        </Space>
      ),
    },
  ]
  
  const expandedRowRender = (record: DistributedStorageRbdImage) => (
    <div data-testid={`rbd-snapshot-list-${record.imageName}`}>
      <SnapshotList 
        image={record} 
        pool={pool}
        teamFilter={teamFilter} 
      />
    </div>
  )
  
  return (
    <>
      <div style={componentStyles.marginBottom.md} data-testid="rbd-image-list-container">
        <Button 
          type="primary" 
          icon={<PlusOutlined />}
          onClick={handleCreate}
          data-testid="rbd-create-image-button"
          style={componentStyles.controlSurface}
        >
          {t('images.create')}
        </Button>
      </div>
      
      <div style={tableStyles.tableContainer}>
        <Table
          columns={columns}
          dataSource={images}
          rowKey="imageGuid"
          loading={isLoading}
          size="small"
          pagination={false}
          data-testid="rbd-image-table"
          onRow={(record) => ({
            'data-testid': `rbd-image-row-${record.imageName}`,
          } as any)}
          expandable={{
            expandedRowRender,
            expandedRowKeys,
            onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as string[]),
            expandIcon: ({ expanded, onExpand, record }) => (
              <Button
                size="small"
                icon={expanded ? <CameraOutlined /> : <CameraOutlined />}
                onClick={e => onExpand(record, e)}
                style={{ ...tableStyles.tableActionButton, marginRight: 8 }}
                data-testid={`rbd-expand-snapshots-${record.imageName}`}
              />
            ),
          }}
        />
      </div>
      
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
              poolVault: data.imageVault,
              vaultVersion: modalState.data?.vaultVersion || 0
            })
          }
          setModalState({ open: false, mode: 'create' })
        }}
        isSubmitting={createImageMutation.isPending || updateImageVaultMutation.isPending}
      />
      
      <QueueItemTraceModal
        visible={queueModalVisible}
        onClose={() => setQueueModalVisible(false)}
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