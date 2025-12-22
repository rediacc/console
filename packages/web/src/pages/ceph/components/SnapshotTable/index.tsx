import { useCallback, useMemo, useState, type Key } from 'react';
import {
  CopyOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  RollbackOutlined,
  SecurityScanOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Button, Flex, Table, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  type CephPool,
  type CephRbdImage,
  type CephRbdSnapshot,
  useCephRbdSnapshots,
} from '@/api/queries/ceph';
import {
  useCreateCephRbdSnapshot,
  useDeleteCephRbdSnapshot,
  useUpdateCephPoolVault,
} from '@/api/queries/cephMutations';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { useExpandableTable, useMessage, useQueueTraceModal } from '@/hooks';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import CloneTable from '@/pages/ceph/components/CloneTable';
import type { SnapshotFormValues as FullSnapshotFormValues } from '@rediacc/shared/types';
import { buildSnapshotColumns } from './columns';
import type { MenuProps } from 'antd';

interface SnapshotTableProps {
  image: CephRbdImage;
  pool: CephPool;
  teamFilter: string | string[];
}

interface SnapshotModalState {
  open: boolean;
  mode: 'create' | 'edit' | 'vault';
  data?: CephRbdSnapshot & { vaultContent?: string | null; vaultVersion?: number };
}

// Form-specific subset of shared SnapshotFormValues (image/pool/team context provided separately)
type SnapshotFormValues = Pick<FullSnapshotFormValues, 'snapshotName'> & { vaultContent: string };

const SnapshotTable: React.FC<SnapshotTableProps> = ({ image, pool, teamFilter }) => {
  const { t } = useTranslation('ceph');
  const message = useMessage();
  const { expandedRowKeys, setExpandedRowKeys } = useExpandableTable();
  const [modalState, setModalState] = useState<SnapshotModalState>({ open: false, mode: 'create' });
  const queueTrace = useQueueTraceModal();
  const managedQueueMutation = useManagedQueueItem();
  const { buildQueueVault } = useQueueVaultBuilder();

  const { data: snapshots = [], isLoading } = useCephRbdSnapshots(String(image.imageGuid));
  const deleteSnapshotMutation = useDeleteCephRbdSnapshot();
  const createSnapshotMutation = useCreateCephRbdSnapshot();
  const updateVaultMutation = useUpdateCephPoolVault();

  const handleCreate = useCallback(() => {
    setModalState({ open: true, mode: 'create' });
  }, []);

  const handleEdit = useCallback((snapshot: CephRbdSnapshot) => {
    setModalState({
      open: true,
      mode: 'edit',
      data: {
        ...snapshot,
        vaultContent: snapshot.vaultContent,
      },
    });
  }, []);

  const handleDelete = useCallback(
    (snapshot: CephRbdSnapshot) => {
      deleteSnapshotMutation.mutate({
        snapshotName: snapshot.snapshotName,
        imageName: image.imageName,
        poolName: pool.poolName,
        teamName: snapshot.teamName,
      });
    },
    [deleteSnapshotMutation, image.imageName, pool.poolName]
  );

  const handleQueueItemCreated = useCallback(
    (taskId: string) => {
      queueTrace.open(taskId);
      message.success('ceph:queue.itemCreated');
    },
    [queueTrace, message]
  );

  const handleRunFunction = useCallback(
    async (functionName: string, snapshot?: CephRbdSnapshot) => {
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
            snapshot_name: snapshot?.snapshotName || '',
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
        message.error('ceph:queue.createError');
      }
    },
    [
      buildQueueVault,
      handleQueueItemCreated,
      image.imageName,
      managedQueueMutation,
      message,
      pool.clusterName,
      pool.poolName,
      pool.teamName,
    ]
  );

  const getSnapshotMenuItems = useCallback(
    (snapshot: CephRbdSnapshot): MenuProps['items'] => [
      {
        key: 'edit',
        label: (
          <Typography.Text data-testid={`snapshot-list-edit-${snapshot.snapshotName}`}>
            {t('snapshots.edit')}
          </Typography.Text>
        ),
        icon: <SettingOutlined />,
        onClick: () => handleEdit(snapshot),
      },
      {
        key: 'vault',
        label: (
          <Typography.Text data-testid={`snapshot-list-vault-${snapshot.snapshotName}`}>
            {t('snapshots.vault')}
          </Typography.Text>
        ),
        icon: <SettingOutlined />,
        onClick: () =>
          setModalState({
            open: true,
            mode: 'vault',
            data: snapshot,
          }),
      },
      {
        key: 'rollback',
        label: (
          <Typography.Text data-testid={`snapshot-list-rollback-${snapshot.snapshotName}`}>
            {t('snapshots.rollback')}
          </Typography.Text>
        ),
        icon: <RollbackOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_snapshot_rollback', snapshot),
      },
      {
        key: 'diff',
        label: (
          <Typography.Text data-testid={`snapshot-list-diff-${snapshot.snapshotName}`}>
            {t('snapshots.diff')}
          </Typography.Text>
        ),
        icon: <InfoCircleOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_diff', snapshot),
      },
      { type: 'divider' },
      {
        key: 'protect',
        label: (
          <Typography.Text data-testid={`snapshot-list-protect-${snapshot.snapshotName}`}>
            {t('snapshots.protect')}
          </Typography.Text>
        ),
        icon: <SecurityScanOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_snapshot_protect', snapshot),
      },
      {
        key: 'unprotect',
        label: (
          <Typography.Text data-testid={`snapshot-list-unprotect-${snapshot.snapshotName}`}>
            {t('snapshots.unprotect')}
          </Typography.Text>
        ),
        icon: <SecurityScanOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_snapshot_unprotect', snapshot),
      },
      { type: 'divider' },
      {
        key: 'delete',
        label: (
          <Typography.Text data-testid={`snapshot-list-delete-${snapshot.snapshotName}`}>
            {t('snapshots.delete')}
          </Typography.Text>
        ),
        icon: <DeleteOutlined />,
        danger: true,
        onClick: () => handleDelete(snapshot),
      },
    ],
    [handleDelete, handleEdit, handleRunFunction, t]
  );

  const columns = useMemo(
    () =>
      buildSnapshotColumns({
        t,
        getSnapshotMenuItems,
        handleRunFunction,
      }),
    [getSnapshotMenuItems, handleRunFunction, t]
  );

  const expandedRowRender = useCallback(
    (record: CephRbdSnapshot) => (
      <CloneTable snapshot={record} image={image} pool={pool} teamFilter={teamFilter} />
    ),
    [image, pool, teamFilter]
  );

  return (
    <>
      <Flex vertical gap={16} data-testid="snapshot-list-container">
        <Typography.Title level={4}>{t('snapshots.title')}</Typography.Title>
        <Flex align="center" wrap>
          <Tooltip title={t('snapshots.create')}>
            <Button
              icon={<PlusOutlined />}
              onClick={handleCreate}
              data-testid="snapshot-list-create-button"
              aria-label={t('snapshots.create')}
            />
          </Tooltip>
        </Flex>

        <Flex className="overflow-hidden">
          <Table<CephRbdSnapshot>
            columns={columns}
            dataSource={snapshots}
            rowKey="snapshotGuid"
            loading={isLoading}
            size="small"
            pagination={false}
            data-testid="snapshot-list-table"
            expandable={{
              expandedRowRender,
              expandedRowKeys,
              onExpandedRowsChange: (keys: readonly Key[]) => setExpandedRowKeys(keys.map(String)),
              expandIcon: ({ onExpand, record }) => (
                <Button
                  icon={<CopyOutlined />}
                  onClick={(event) => onExpand(record, event)}
                  data-testid={`snapshot-list-expand-${record.snapshotName}`}
                />
              ),
            }}
          />
        </Flex>
      </Flex>

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
          vaultContent: modalState.data?.vaultContent,
        }}
        teamFilter={pool.teamName}
        onSubmit={async (data) => {
          const snapshotData = data as SnapshotFormValues;
          if (modalState.mode === 'create') {
            await createSnapshotMutation.mutateAsync({
              imageName: image.imageName,
              poolName: pool.poolName,
              teamName: pool.teamName,
              snapshotName: snapshotData.snapshotName,
              vaultContent: snapshotData.vaultContent,
            });
          } else if (modalState.mode === 'edit') {
            await updateVaultMutation.mutateAsync({
              poolName: pool.poolName,
              teamName: pool.teamName,
              vaultContent: snapshotData.vaultContent,
              vaultVersion: modalState.data?.vaultVersion || 0,
            });
          }
          setModalState({ open: false, mode: 'create' });
        }}
        isSubmitting={createSnapshotMutation.isPending || updateVaultMutation.isPending}
        data-testid={`snapshot-list-modal-${modalState.mode}`}
      />

      <QueueItemTraceModal
        open={queueTrace.state.open}
        onCancel={queueTrace.close}
        taskId={queueTrace.state.taskId}
        data-testid="snapshot-list-queue-modal"
      />
    </>
  );
};

export default SnapshotTable;
