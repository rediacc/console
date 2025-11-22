import { useCallback, useMemo, useState } from 'react'
import { Table, Tooltip, message } from 'antd'
import {
  PlusOutlined,
  SettingOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  CloudUploadOutlined,
  TeamOutlined,
  SyncOutlined,
  ScissorOutlined,
  CopyOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { useTranslation } from 'react-i18next'
import {
  useDistributedStorageRbdClones,
  useDeleteDistributedStorageRbdClone,
  useCreateDistributedStorageRbdClone,
  useUpdateDistributedStoragePoolVault,
  type DistributedStorageRbdClone,
  type DistributedStorageRbdSnapshot,
  type DistributedStorageRbdImage,
  type DistributedStoragePool,
} from '@/api/queries/distributedStorage'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { AssignMachinesToCloneModal } from '@/components/resources/AssignMachinesToCloneModal'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { buildCloneColumns } from './columns'
import {
  ActionsRow,
  Container,
  CreateButton,
  ExpandButton,
  TableWrapper,
  Title,
} from './styles'
import { CloneMachineList } from './components/CloneMachineList'
import { MachineCountBadge } from './components/MachineCountBadge'

interface CloneListProps {
  snapshot: DistributedStorageRbdSnapshot
  image: DistributedStorageRbdImage
  pool: DistributedStoragePool
  teamFilter: string | string[]
}

const CloneList: React.FC<CloneListProps> = ({ snapshot, image, pool }) => {
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

  const handleCreate = useCallback(() => {
    setModalState({ open: true, mode: 'create' })
  }, [])

  const handleEdit = useCallback((clone: DistributedStorageRbdClone) => {
    setModalState({
      open: true,
      mode: 'edit',
      data: {
        ...clone,
        vaultContent: clone.vaultContent || clone.cloneVault,
      },
    })
  }, [])

  const handleDelete = useCallback(
    (clone: DistributedStorageRbdClone) => {
      deleteCloneMutation.mutate({
        cloneName: clone.cloneName,
        snapshotName: snapshot.snapshotName,
        imageName: image.imageName,
        poolName: pool.poolName,
        teamName: clone.teamName,
      })
    },
    [deleteCloneMutation, image.imageName, pool.poolName, snapshot.snapshotName],
  )

  const handleQueueItemCreated = useCallback(
    (taskId: string) => {
      setQueueModalTaskId(taskId)
      setQueueModalVisible(true)
      message.success(t('queue.itemCreated'))
    },
    [t],
  )

  const handleManageMachines = useCallback((clone: DistributedStorageRbdClone) => {
    setMachineModalState({ open: true, clone })
  }, [])

  const handleRunFunction = useCallback(
    async (functionName: string, clone?: DistributedStorageRbdClone) => {
      try {
        const queueVault = await buildQueueVault({
          functionName,
          teamName: pool.teamName,
          machineName: pool.clusterName,
          bridgeName: 'default',
          params: {
            cluster_name: pool.clusterName,
            pool_name: pool.poolName,
            image_name: image.imageName,
            snapshot_name: snapshot.snapshotName,
            clone_name: clone?.cloneName || '',
          },
          priority: 3,
          description: `Execute ${functionName}`,
          addedVia: 'DistributedStorage',
        })

        const response = await managedQueueMutation.mutateAsync({
          teamName: pool.teamName,
          machineName: pool.clusterName,
          bridgeName: 'default',
          queueVault,
          priority: 3,
        })

        if (response.taskId) {
          handleQueueItemCreated(response.taskId)
        }
      } catch (error) {
        message.error(t('queue.createError'))
      }
    },
    [
      buildQueueVault,
      handleQueueItemCreated,
      image.imageName,
      managedQueueMutation,
      pool.clusterName,
      pool.poolName,
      pool.teamName,
      snapshot.snapshotName,
      t,
    ],
  )

  const getCloneMenuItems = useCallback(
    (clone: DistributedStorageRbdClone): MenuProps['items'] => [
      {
        key: 'edit',
        label: t('clones.edit'),
        icon: <SettingOutlined />,
        onClick: () => handleEdit(clone),
        'data-testid': `clone-list-edit-${clone.cloneName}`,
      },
      {
        key: 'manageMachines',
        label: t('clones.manageMachines'),
        icon: <TeamOutlined />,
        onClick: () => handleManageMachines(clone),
        'data-testid': `clone-list-manage-machines-${clone.cloneName}`,
      },
      { type: 'divider' },
      {
        key: 'flatten',
        label: t('clones.flatten'),
        icon: <SyncOutlined />,
        onClick: () => handleRunFunction('distributed_storage_rbd_flatten', clone),
        'data-testid': `clone-list-flatten-${clone.cloneName}`,
      },
      {
        key: 'split',
        label: t('clones.split'),
        icon: <ScissorOutlined />,
        onClick: () => handleRunFunction('distributed_storage_rbd_clone_split', clone),
        'data-testid': `clone-list-split-${clone.cloneName}`,
      },
      { type: 'divider' },
      {
        key: 'export',
        label: t('clones.export'),
        icon: <CloudUploadOutlined />,
        onClick: () => handleRunFunction('distributed_storage_rbd_export', clone),
        'data-testid': `clone-list-export-${clone.cloneName}`,
      },
      {
        key: 'info',
        label: t('clones.info'),
        icon: <InfoCircleOutlined />,
        onClick: () => handleRunFunction('distributed_storage_rbd_info', clone),
        'data-testid': `clone-list-info-${clone.cloneName}`,
      },
      { type: 'divider' },
      {
        key: 'delete',
        label: t('clones.delete'),
        icon: <DeleteOutlined />,
        danger: true,
        onClick: () => handleDelete(clone),
        'data-testid': `clone-list-delete-${clone.cloneName}`,
      },
    ],
    [handleDelete, handleEdit, handleManageMachines, handleRunFunction, t],
  )

  const renderMachineCount = useCallback(
    (clone: DistributedStorageRbdClone) => (
      <MachineCountBadge
        clone={clone}
        snapshotName={snapshot.snapshotName}
        imageName={image.imageName}
        poolName={pool.poolName}
        teamName={pool.teamName}
      />
    ),
    [image.imageName, pool.poolName, pool.teamName, snapshot.snapshotName],
  )

  const columns = useMemo(
    () =>
      buildCloneColumns({
        t,
        renderMachineCount,
        handleRunFunction,
        getCloneMenuItems,
      }),
    [getCloneMenuItems, handleRunFunction, renderMachineCount, t],
  )

  const expandedRowRender = useCallback(
    (record: DistributedStorageRbdClone) => (
      <CloneMachineList
        clone={record}
        snapshot={snapshot}
        image={image}
        pool={pool}
        onManageMachines={handleManageMachines}
      />
    ),
    [handleManageMachines, image, pool, snapshot],
  )

  return (
    <>
      <Container data-testid="clone-list-container">
        <Title>{t('clones.title')}</Title>
        <ActionsRow>
          <Tooltip title={t('clones.create')}>
            <CreateButton
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreate}
              size="small"
              data-testid="clone-list-create-button"
            >
              {t('clones.create')}
            </CreateButton>
          </Tooltip>
        </ActionsRow>

        <TableWrapper>
          <Table
            columns={columns}
            dataSource={clones}
            rowKey="cloneGuid"
            loading={isLoading}
            size="small"
            pagination={false}
            data-testid="clone-list-table"
            expandable={{
              expandedRowRender,
              rowExpandable: () => true,
              expandedRowKeys,
              onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as string[]),
              expandIcon: ({ onExpand, record }) => (
                <ExpandButton
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={(event) => onExpand(record, event)}
                  data-testid={`clone-list-expand-${record.cloneName}`}
                />
              ),
            }}
          />
        </TableWrapper>
      </Container>

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
          vaultContent: modalState.data?.vaultContent || modalState.data?.cloneVault,
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
              cloneVault: data.cloneVault,
            })
          } else if (modalState.mode === 'edit') {
            await updateVaultMutation.mutateAsync({
              poolName: pool.poolName,
              teamName: pool.teamName,
              poolVault: data.cloneVault,
              vaultVersion: modalState.data?.vaultVersion || 0,
            })
          }
          setModalState({ open: false, mode: 'create' })
        }}
        isSubmitting={createCloneMutation.isPending || updateVaultMutation.isPending}
      />
      <QueueItemTraceModal
        visible={queueModalVisible}
        onClose={() => setQueueModalVisible(false)}
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
        }}
      />
    </>
  )
}

export default CloneList
