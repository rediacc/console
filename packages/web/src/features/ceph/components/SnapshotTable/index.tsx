import {
  CameraOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  RollbackOutlined,
  SecurityScanOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type {
  GetCephRbdImages_ResultSet1 as CephImage,
  GetCephPools_ResultSet1 as CephPool,
  GetCephRbdSnapshots_ResultSet1 as CephSnapshot,
  CreateCephRbdSnapshotParams,
} from '@rediacc/shared/types';
import type { MenuProps } from 'antd';
import { Button, Flex, Space, Tag, Tooltip, Typography } from 'antd';
import { type Key, useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useCreateCephRbdSnapshot,
  useDeleteCephRbdSnapshot,
  useGetCephRbdSnapshots,
  useUpdateCephPoolVault,
} from '@/api/api-hooks.generated';
import { MobileCard } from '@/components/common/MobileCard';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import CloneTable from '@/features/ceph/components/CloneTable';
import { useExpandableTable, useMessage, useQueueTraceModal } from '@/hooks';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { buildSnapshotColumns } from './columns';

interface SnapshotTableProps {
  image: CephImage;
  pool: CephPool;
  teamFilter: string | string[];
}

interface SnapshotModalState {
  open: boolean;
  mode: 'create' | 'edit' | 'vault';
  data?: CephSnapshot & { vaultContent?: string | null; vaultVersion?: number };
}

// Form-specific subset (image/pool/team context provided separately)
// Note: vaultContent and vaultVersion are already optional in generated types
type SnapshotFormValues = Pick<CreateCephRbdSnapshotParams, 'snapshotName'> & {
  vaultContent: string; // Required for form
};

const SnapshotTable: React.FC<SnapshotTableProps> = ({ image, pool, teamFilter }) => {
  const { t } = useTranslation('ceph');
  const message = useMessage();
  const { expandedRowKeys, setExpandedRowKeys } = useExpandableTable();
  const [modalState, setModalState] = useState<SnapshotModalState>({ open: false, mode: 'create' });
  const queueTrace = useQueueTraceModal();
  const managedQueueMutation = useManagedQueueItem();
  const { buildQueueVault } = useQueueVaultBuilder();

  const { data: snapshots = [], isLoading } = useGetCephRbdSnapshots(String(image.imageGuid));
  const deleteSnapshotMutation = useDeleteCephRbdSnapshot();
  const createSnapshotMutation = useCreateCephRbdSnapshot();
  const updateVaultMutation = useUpdateCephPoolVault();

  const handleCreate = useCallback(() => {
    setModalState({ open: true, mode: 'create' });
  }, []);

  const handleEdit = useCallback((snapshot: CephSnapshot) => {
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
    (snapshot: CephSnapshot) => {
      deleteSnapshotMutation.mutate({
        snapshotName: snapshot.snapshotName ?? '',
        imageName: image.imageName ?? '',
        poolName: pool.poolName ?? '',
        teamName: snapshot.teamName ?? '',
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
    async (functionName: string, snapshot?: CephSnapshot) => {
      try {
        const queueVault = await buildQueueVault({
          functionName,
          teamName: pool.teamName ?? '',
          machineName: pool.clusterName ?? '',
          bridgeName: 'default',
          params: {
            cluster_name: pool.clusterName ?? '',
            pool_name: pool.poolName ?? '',
            image_name: image.imageName ?? '',
            snapshot_name: snapshot?.snapshotName ?? '',
          },
          priority: 3,
          addedVia: 'Ceph',
        });

        const response = await managedQueueMutation.mutateAsync({
          teamName: pool.teamName ?? '',
          machineName: pool.clusterName ?? '',
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
    (snapshot: CephSnapshot): MenuProps['items'] => [
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

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: CephSnapshot) => {
      const onExpand = () => {
        setExpandedRowKeys((prev) =>
          prev.includes(record.snapshotGuid ?? '')
            ? prev.filter((k) => k !== record.snapshotGuid)
            : [...prev, record.snapshotGuid ?? '']
        );
      };

      const actions = (
        <Space>
          <Tooltip title={t('clones.title')}>
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={onExpand}
              aria-label={t('clones.title')}
              data-testid={`snapshot-clones-${record.snapshotName}`}
            />
          </Tooltip>
          <Tooltip title={t('common:actions.remote')}>
            <Button
              type="text"
              size="small"
              icon={<CloudUploadOutlined />}
              onClick={() => handleRunFunction('ceph_rbd_snapshot_list', record)}
              aria-label={t('common:actions.remote')}
              data-testid={`snapshot-info-${record.snapshotName}`}
            />
          </Tooltip>
          <ResourceActionsDropdown menuItems={getSnapshotMenuItems(record)} />
        </Space>
      );

      return (
        <MobileCard actions={actions}>
          <Space>
            <CameraOutlined />
            <Typography.Text strong>{record.snapshotName}</Typography.Text>
            {record.vaultContent && <Tag bordered={false}>{t('common.vault')}</Tag>}
          </Space>
          <Typography.Text type="secondary" className="text-xs truncate">
            {record.snapshotGuid?.substring(0, 8)}...
          </Typography.Text>
        </MobileCard>
      );
    },
    [t, getSnapshotMenuItems, handleRunFunction, setExpandedRowKeys]
  );

  const expandedRowRender = useCallback(
    (record: CephSnapshot) => (
      <CloneTable snapshot={record} image={image} pool={pool} teamFilter={teamFilter} />
    ),
    [image, pool, teamFilter]
  );

  const isSubmitting = [createSnapshotMutation.isPending, updateVaultMutation.isPending].some(
    Boolean
  );

  return (
    <>
      <Flex vertical data-testid="snapshot-list-container">
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
          <ResourceListView<CephSnapshot>
            columns={columns}
            data={snapshots}
            rowKey="snapshotGuid"
            loading={isLoading}
            pagination={false}
            data-testid="snapshot-list-table"
            mobileRender={mobileRender}
            expandable={{
              expandedRowRender,
              expandedRowKeys,
              onExpandedRowsChange: (keys: readonly Key[]) => setExpandedRowKeys(keys.map(String)),
              expandIcon: ({
                onExpand,
                record,
              }: {
                onExpand: (record: CephSnapshot, event: React.MouseEvent<HTMLElement>) => void;
                record: CephSnapshot;
              }) => (
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
          teamName: pool.teamName ?? '',
          poolName: pool.poolName ?? '',
          imageName: image.imageName ?? '',
          pools: [{ poolName: pool.poolName ?? '', clusterName: pool.clusterName ?? '' }],
          images: [{ imageName: image.imageName ?? '' }],
          vaultContent: modalState.data?.vaultContent,
        }}
        teamFilter={pool.teamName ?? ''}
        onSubmit={async (data) => {
          const snapshotData = data as SnapshotFormValues;
          if (modalState.mode === 'create') {
            await createSnapshotMutation.mutateAsync({
              imageName: image.imageName ?? '',
              poolName: pool.poolName ?? '',
              teamName: pool.teamName ?? '',
              snapshotName: snapshotData.snapshotName,
              vaultContent: snapshotData.vaultContent,
            });
          } else if (modalState.mode === 'edit') {
            await updateVaultMutation.mutateAsync({
              poolName: pool.poolName ?? '',
              teamName: pool.teamName ?? '',
              vaultContent: snapshotData.vaultContent,
              vaultVersion: modalState.data?.vaultVersion ?? 0,
            });
          }
          setModalState({ open: false, mode: 'create' });
        }}
        isSubmitting={isSubmitting}
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
