import { useCallback, useMemo, useState, type Key } from 'react';
import {
  CameraOutlined,
  CheckCircleOutlined,
  CloudDownloadOutlined,
  CloudServerOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  DeleteOutlined,
  DesktopOutlined,
  ExpandOutlined,
  FileImageOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  SettingOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { Button, Flex, Space, Tag, Tooltip, Typography, type MenuProps } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  type CephPool,
  type CephRbdImage,
  useAvailableMachinesForClone,
  useCephRbdImages,
} from '@/api/queries/ceph';
import {
  useCreateCephRbdImage,
  useDeleteCephRbdImage,
  useUpdateCephPoolVault,
} from '@/api/queries/cephMutations';
import { MobileCard } from '@/components/common/MobileCard';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { ImageMachineReassignmentModal } from '@/features/ceph/components/modals/ImageMachineReassignmentModal';
import { useDialogState, useExpandableTable, useMessage, useQueueTraceModal } from '@/hooks';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import type { ImageFormValues as FullImageFormValues } from '@rediacc/shared/types';
import { buildRbdImageColumns } from './columns';
import SnapshotTable from '../SnapshotTable';

interface RbdImageTableProps {
  pool: CephPool;
  teamFilter: string | string[];
}

interface RbdImageModalState {
  open: boolean;
  mode: 'create' | 'edit' | 'vault';
  data?: CephRbdImage & { vaultContent?: string | null; vaultVersion?: number };
}

// Form-specific subset of shared ImageFormValues (pool/team context provided separately)
type ImageFormValues = Pick<FullImageFormValues, 'imageName' | 'machineName'> & {
  vaultContent: string;
};

const RbdImageTable: React.FC<RbdImageTableProps> = ({ pool, teamFilter }) => {
  const { t } = useTranslation('ceph');
  const message = useMessage();
  const { expandedRowKeys, setExpandedRowKeys } = useExpandableTable();
  const [modalState, setModalState] = useState<RbdImageModalState>({ open: false, mode: 'create' });
  const queueTrace = useQueueTraceModal();
  const reassignMachineModal = useDialogState<CephRbdImage>();
  const managedQueueMutation = useManagedQueueItem();
  const { buildQueueVault } = useQueueVaultBuilder();

  const { data: images = [], isLoading } = useCephRbdImages(pool.poolGuid ?? undefined);
  const deleteImageMutation = useDeleteCephRbdImage();
  const createImageMutation = useCreateCephRbdImage();
  const updateImageVaultMutation = useUpdateCephPoolVault();

  // Fetch available machines for the team
  const { data: availableMachines = [] } = useAvailableMachinesForClone(
    pool.teamName,
    modalState.open && modalState.mode === 'create'
  );
  const getRowProps = (record: CephRbdImage): Record<string, unknown> => ({
    'data-testid': `rbd-image-row-${record.imageName}`,
  });

  const handleCreate = () => {
    setModalState({ open: true, mode: 'create' });
  };

  const handleEdit = (image: CephRbdImage) => {
    setModalState({
      open: true,
      mode: 'edit',
      data: {
        ...image,
        vaultContent: image.vaultContent,
      },
    });
  };

  const handleDelete = (image: CephRbdImage) => {
    deleteImageMutation.mutate({
      imageName: image.imageName,
      poolName: pool.poolName,
      teamName: image.teamName,
    });
  };

  const handleReassignMachine = (image: CephRbdImage) => {
    reassignMachineModal.open(image);
  };

  const handleQueueItemCreated = useCallback(
    (taskId: string) => {
      queueTrace.open(taskId);
      message.success('ceph:queue.itemCreated');
    },
    [queueTrace, message]
  );

  const handleRunFunction = useCallback(
    async (functionName: string, image?: CephRbdImage) => {
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
          addedVia: 'Ceph',
        });

        const response = await managedQueueMutation.mutateAsync({
          teamName: pool.teamName,
          machineName: pool.clusterName, // Using cluster as machine for Ceph
          bridgeName: 'default',
          queueVault,
          priority: 3,
        });

        const taskId = response.taskId;
        if (taskId) {
          handleQueueItemCreated(taskId);
        }
      } catch {
        message.error('ceph:queue.createError');
      }
    },
    [pool, buildQueueVault, managedQueueMutation, handleQueueItemCreated, message]
  );

  const getImageMenuItems = useCallback(
    (image: CephRbdImage): MenuProps['items'] => [
      {
        key: 'edit',
        label: (
          <Typography.Text data-testid={`rbd-edit-action-${image.imageName}`}>
            {t('images.edit')}
          </Typography.Text>
        ),
        icon: <SettingOutlined />,
        onClick: () => handleEdit(image),
      },
      {
        key: 'reassignMachine',
        label: (
          <Typography.Text data-testid={`rbd-reassign-action-${image.imageName}`}>
            {t('images.reassignMachine')}
          </Typography.Text>
        ),
        icon: <CloudServerOutlined />,
        onClick: () => handleReassignMachine(image),
      },
      { type: 'divider' },
      {
        key: 'snapshot',
        label: (
          <Typography.Text data-testid={`rbd-snapshot-action-${image.imageName}`}>
            {t('images.createSnapshot')}
          </Typography.Text>
        ),
        icon: <CameraOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_snapshot_create', image),
      },
      {
        key: 'clone',
        label: (
          <Typography.Text data-testid={`rbd-clone-action-${image.imageName}`}>
            {t('images.clone')}
          </Typography.Text>
        ),
        icon: <CopyOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_clone', image),
      },
      {
        key: 'resize',
        label: (
          <Typography.Text data-testid={`rbd-resize-action-${image.imageName}`}>
            {t('images.resize')}
          </Typography.Text>
        ),
        icon: <ExpandOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_resize', image),
      },
      { type: 'divider' },
      {
        key: 'export',
        label: (
          <Typography.Text data-testid={`rbd-export-action-${image.imageName}`}>
            {t('images.export')}
          </Typography.Text>
        ),
        icon: <CloudUploadOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_export', image),
      },
      {
        key: 'import',
        label: (
          <Typography.Text data-testid={`rbd-import-action-${image.imageName}`}>
            {t('images.import')}
          </Typography.Text>
        ),
        icon: <CloudDownloadOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_import', image),
      },
      { type: 'divider' },
      {
        key: 'info',
        label: (
          <Typography.Text data-testid={`rbd-info-action-${image.imageName}`}>
            {t('images.info')}
          </Typography.Text>
        ),
        icon: <InfoCircleOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_info', image),
      },
      {
        key: 'status',
        label: (
          <Typography.Text data-testid={`rbd-status-action-${image.imageName}`}>
            {t('images.status')}
          </Typography.Text>
        ),
        icon: <CheckCircleOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_status', image),
      },
      { type: 'divider' },
      {
        key: 'map',
        label: (
          <Typography.Text data-testid={`rbd-map-action-${image.imageName}`}>
            {t('images.map')}
          </Typography.Text>
        ),
        icon: <DesktopOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_map', image),
      },
      {
        key: 'unmap',
        label: (
          <Typography.Text data-testid={`rbd-unmap-action-${image.imageName}`}>
            {t('images.unmap')}
          </Typography.Text>
        ),
        icon: <DesktopOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_unmap', image),
      },
      {
        key: 'showmapped',
        label: (
          <Typography.Text data-testid={`rbd-showmapped-action-${image.imageName}`}>
            {t('images.showMapped')}
          </Typography.Text>
        ),
        icon: <DesktopOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_showmapped', image),
      },
      { type: 'divider' },
      {
        key: 'flatten',
        label: (
          <Typography.Text data-testid={`rbd-flatten-action-${image.imageName}`}>
            {t('images.flatten')}
          </Typography.Text>
        ),
        icon: <SyncOutlined />,
        onClick: () => handleRunFunction('ceph_rbd_flatten', image),
      },
      { type: 'divider' },
      {
        key: 'delete',
        label: (
          <Typography.Text data-testid={`rbd-delete-action-${image.imageName}`}>
            {t('images.delete')}
          </Typography.Text>
        ),
        icon: <DeleteOutlined />,
        danger: true,
        onClick: () => handleDelete(image),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, handleRunFunction]
  );

  const columns = useMemo(
    () =>
      buildRbdImageColumns({
        t,
        handleRunFunction,
        getImageMenuItems,
      }),
    [t, handleRunFunction, getImageMenuItems]
  );

  const handleExpand = useCallback(
    (image: CephRbdImage) => {
      const imageKey = String(image.imageGuid ?? '');
      setExpandedRowKeys((prev) =>
        prev.includes(imageKey) ? prev.filter((k) => k !== imageKey) : [...prev, imageKey]
      );
    },
    [setExpandedRowKeys]
  );

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: CephRbdImage) => {
      const actions = (
        <Space>
          <Tooltip title={t('snapshots.title')}>
            <Button
              type="text"
              size="small"
              icon={<CameraOutlined />}
              onClick={() => handleExpand(record)}
              aria-label={t('snapshots.title')}
            />
          </Tooltip>
          <Tooltip title={t('common.remote')}>
            <Button
              type="text"
              size="small"
              icon={<CloudUploadOutlined />}
              onClick={() => handleRunFunction('ceph_rbd_info', record)}
              aria-label={t('common.remote')}
            />
          </Tooltip>
          <ResourceActionsDropdown menuItems={getImageMenuItems(record)} />
        </Space>
      );

      return (
        <MobileCard actions={actions}>
          <Space>
            <FileImageOutlined />
            <Typography.Text strong>{record.imageName}</Typography.Text>
            {record.vaultContent && <Tag bordered={false}>{t('common.vault')}</Tag>}
          </Space>
          <Typography.Text type="secondary" className="text-xs truncate">
            {String(record.imageGuid ?? '').substring(0, 8)}...
          </Typography.Text>
          {record.machineName ? (
            <Tag icon={<CloudServerOutlined />} bordered={false}>
              {record.machineName}
            </Tag>
          ) : (
            <Tag bordered={false}>{t('common.none')}</Tag>
          )}
        </MobileCard>
      );
    },
    [t, getImageMenuItems, handleRunFunction, handleExpand]
  );

  const expandedRowRender = (record: CephRbdImage) => (
    <Flex data-testid={`rbd-snapshot-list-${record.imageName}`}>
      <SnapshotTable image={record} pool={pool} teamFilter={teamFilter} />
    </Flex>
  );

  return (
    <>
      <Flex data-testid="rbd-image-list-container">
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleCreate}
          data-testid="rbd-create-image-button"
          // eslint-disable-next-line no-restricted-syntax
          style={{ minHeight: 40 }}
        >
          {t('images.create')}
        </Button>
      </Flex>

      <Flex className="overflow-hidden">
        <ResourceListView<CephRbdImage>
          columns={columns}
          data={images}
          rowKey="imageGuid"
          loading={isLoading}
          pagination={false}
          data-testid="rbd-image-table"
          onRow={getRowProps}
          mobileRender={mobileRender}
          expandable={{
            expandedRowRender,
            expandedRowKeys,
            onExpandedRowsChange: (keys: readonly Key[]) => setExpandedRowKeys(keys.map(String)),
            expandIcon: ({
              expanded,
              onExpand,
              record,
            }: {
              expanded: boolean;
              onExpand: (record: CephRbdImage, event: React.MouseEvent<HTMLElement>) => void;
              record: CephRbdImage;
            }) => (
              <Button
                icon={expanded ? <CameraOutlined /> : <CameraOutlined />}
                onClick={(e) => onExpand(record, e)}
                data-testid={`rbd-expand-snapshots-${record.imageName}`}
              />
            ),
          }}
        />
      </Flex>

      <UnifiedResourceModal
        open={modalState.open}
        onCancel={() => setModalState({ open: false, mode: 'create' })}
        resourceType="image"
        mode={modalState.mode}
        existingData={{
          ...modalState.data,
          machineName: modalState.data?.machineName ?? undefined,
          teamName: pool.teamName,
          poolName: pool.poolName,
          pools: [pool],
          availableMachines: availableMachines.map((machine) => ({
            machineName: machine.machineName ?? '',
            bridgeName: machine.bridgeName ?? '',
            regionName: machine.regionName ?? '',
            status: machine.status,
          })),
          vaultContent: modalState.data?.vaultContent ?? undefined,
        }}
        teamFilter={pool.teamName}
        onSubmit={async (data) => {
          const imageData = data as ImageFormValues;
          if (modalState.mode === 'create') {
            await createImageMutation.mutateAsync({
              poolName: pool.poolName,
              teamName: pool.teamName,
              imageName: imageData.imageName,
              machineName: imageData.machineName,
              vaultContent: imageData.vaultContent,
            });
          } else if (modalState.mode === 'edit') {
            await updateImageVaultMutation.mutateAsync({
              poolName: pool.poolName,
              teamName: pool.teamName,
              vaultContent: imageData.vaultContent,
              vaultVersion: modalState.data?.vaultVersion || 0,
            });
          }
          setModalState({ open: false, mode: 'create' });
        }}
        isSubmitting={createImageMutation.isPending || updateImageVaultMutation.isPending}
      />

      <QueueItemTraceModal
        open={queueTrace.state.open}
        onCancel={queueTrace.close}
        taskId={queueTrace.state.taskId}
      />

      {reassignMachineModal.state.data && (
        <ImageMachineReassignmentModal
          open={reassignMachineModal.isOpen}
          image={reassignMachineModal.state.data}
          teamName={pool.teamName}
          poolName={pool.poolName}
          onCancel={reassignMachineModal.close}
          onSuccess={() => {
            reassignMachineModal.close();
            // The query will automatically refresh due to invalidation in the mutation
          }}
        />
      )}
    </>
  );
};

export default RbdImageTable;
