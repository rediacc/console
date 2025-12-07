import { useCallback, useMemo, useState } from 'react';
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
} from '@ant-design/icons';
import { Table, Tooltip, message } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  useCephRbdClones,
  type CephRbdClone,
  type CephRbdSnapshot,
  type CephRbdImage,
  type CephPool,
} from '@/api/queries/ceph';
import {
  useDeleteCephRbdClone,
  useCreateCephRbdClone,
  useUpdateCephPoolVault,
} from '@/api/queries/cephMutations';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { RediaccButton } from '@/components/ui';
import { useDialogState, useQueueTraceModal } from '@/hooks/useDialogState';
import { useFormModal } from '@/hooks/useFormModal';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { AssignMachinesToCloneModal } from '@/pages/ceph/components/AssignMachinesToCloneModal';
import { buildCloneColumns } from './columns';
import { CloneMachineTable } from './components/CloneMachineTable';
import { MachineCountBadge } from './components/MachineCountBadge';
import { ActionsRow, Container, ExpandButton, TableWrapper, Title } from './styles';
import type { MenuProps } from 'antd';

interface CloneTableProps {
  snapshot: CephRbdSnapshot;
  image: CephRbdImage;
  pool: CephPool;
  teamFilter: string | string[];
}

type CloneModalData = CephRbdClone & {
  vaultContent?: string;
  vaultVersion?: number;
};

const CloneTable: React.FC<CloneTableProps> = ({ snapshot, image, pool }) => {
  const { t } = useTranslation('ceph');
  const cloneModal = useFormModal<CloneModalData>();
  const queueTrace = useQueueTraceModal();
  const machineModal = useDialogState<CephRbdClone>();
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);

  const managedQueueMutation = useManagedQueueItem();
  const { buildQueueVault } = useQueueVaultBuilder();

  const { data: clones = [], isLoading } = useCephRbdClones(snapshot.snapshotGuid);
  const deleteCloneMutation = useDeleteCephRbdClone();
  const createCloneMutation = useCreateCephRbdClone();
  const updateVaultMutation = useUpdateCephPoolVault();

  const handleCreate = useCallback(() => {
    cloneModal.openCreate();
  }, [cloneModal]);

  const handleEdit = useCallback(
    (clone: CephRbdClone) => {
      cloneModal.openEdit({
        ...clone,
        vaultContent: clone.vaultContent,
      });
    },
    [cloneModal]
  );

  const handleDelete = useCallback(
    (clone: CephRbdClone) => {
      deleteCloneMutation.mutate({
        cloneName: clone.cloneName,
        snapshotName: snapshot.snapshotName,
        imageName: image.imageName,
        poolName: pool.poolName,
        teamName: clone.teamName,
      });
    },
    [deleteCloneMutation, image.imageName, pool.poolName, snapshot.snapshotName]
  );

  const handleQueueItemCreated = useCallback(
    (taskId: string) => {
      queueTrace.open(taskId);
      message.success(t('queue.itemCreated'));
    },
    [t, queueTrace]
  );

  const handleManageMachines = useCallback(
    (clone: CephRbdClone) => {
      machineModal.open(clone);
    },
    [machineModal]
  );

  const handleRunFunction = useCallback(
    async (functionName: string, clone?: CephRbdClone) => {
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
          addedVia: 'Ceph',
        });

        const response = await managedQueueMutation.mutateAsync({
          teamName: pool.teamName,
          machineName: pool.clusterName,
          bridgeName: 'default',
          queueVault,
          priority: 3,
        });

        if (response.taskId) {
          handleQueueItemCreated(response.taskId);
        }
      } catch {
        message.error(t('queue.createError'));
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
    ]
  );

  const getCloneMenuItems = useCallback(
    (clone: CephRbdClone): MenuProps['items'] => [
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
        onClick: () => handleRunFunction('ceph_rbd_flatten', clone),
        'data-testid': `clone-list-flatten-${clone.cloneName}`,
      },
      {
        key: 'split',
        label: t('clones.split'),
        icon: <ScissorOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_clone_split', clone),
        'data-testid': `clone-list-split-${clone.cloneName}`,
      },
      { type: 'divider' },
      {
        key: 'export',
        label: t('clones.export'),
        icon: <CloudUploadOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_export', clone),
        'data-testid': `clone-list-export-${clone.cloneName}`,
      },
      {
        key: 'info',
        label: t('clones.info'),
        icon: <InfoCircleOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_info', clone),
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
    [handleDelete, handleEdit, handleManageMachines, handleRunFunction, t]
  );

  const renderMachineCount = useCallback(
    (clone: CephRbdClone) => (
      <MachineCountBadge
        clone={clone}
        snapshotName={snapshot.snapshotName}
        imageName={image.imageName}
        poolName={pool.poolName}
        teamName={pool.teamName}
      />
    ),
    [image.imageName, pool.poolName, pool.teamName, snapshot.snapshotName]
  );

  const columns = useMemo(
    () =>
      buildCloneColumns({
        t,
        renderMachineCount,
        handleRunFunction,
        getCloneMenuItems,
      }),
    [getCloneMenuItems, handleRunFunction, renderMachineCount, t]
  );

  const expandedRowRender = useCallback(
    (record: CephRbdClone) => (
      <CloneMachineTable
        clone={record}
        snapshot={snapshot}
        image={image}
        pool={pool}
        onManageMachines={handleManageMachines}
      />
    ),
    [handleManageMachines, image, pool, snapshot]
  );

  return (
    <>
      <Container data-testid="clone-list-container">
        <Title>{t('clones.title')}</Title>
        <ActionsRow>
          <Tooltip title={t('clones.create')}>
            <RediaccButton
              icon={<PlusOutlined />}
              onClick={handleCreate}
              data-testid="clone-list-create-button"
            >
              {t('clones.create')}
            </RediaccButton>
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
        open={cloneModal.isOpen}
        onCancel={cloneModal.close}
        resourceType="clone"
        mode={cloneModal.mode}
        existingData={{
          ...(cloneModal.state.data ?? {}),
          teamName: pool.teamName,
          poolName: pool.poolName,
          imageName: image.imageName,
          snapshotName: snapshot.snapshotName,
          pools: [pool],
          images: [image],
          snapshots: [snapshot],
          vaultContent: cloneModal.state.data?.vaultContent,
        }}
        teamFilter={pool.teamName}
        onSubmit={async (formValues) => {
          const data = formValues as { cloneName: string; vaultContent: string };
          if (cloneModal.mode === 'create') {
            await createCloneMutation.mutateAsync({
              snapshotName: snapshot.snapshotName,
              imageName: image.imageName,
              poolName: pool.poolName,
              teamName: pool.teamName,
              cloneName: data.cloneName,
              vaultContent: data.vaultContent,
            });
          } else if (cloneModal.mode === 'edit') {
            await updateVaultMutation.mutateAsync({
              poolName: pool.poolName,
              teamName: pool.teamName,
              vaultContent: data.vaultContent,
              vaultVersion: cloneModal.state.data?.vaultVersion || 0,
            });
          }
          cloneModal.close();
        }}
        isSubmitting={createCloneMutation.isPending || updateVaultMutation.isPending}
      />
      <QueueItemTraceModal
        open={queueTrace.state.open}
        onCancel={queueTrace.close}
        taskId={queueTrace.state.taskId}
      />

      <AssignMachinesToCloneModal
        open={machineModal.isOpen}
        clone={machineModal.state.data}
        poolName={pool.poolName}
        imageName={image.imageName}
        snapshotName={snapshot.snapshotName}
        teamName={pool.teamName}
        onCancel={machineModal.close}
        onSuccess={machineModal.close}
      />
    </>
  );
};

export default CloneTable;
