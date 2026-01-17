import React, { useMemo } from 'react';
import { Flex, type MenuProps, Modal, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  useCreateStorage,
  useDeleteStorage,
  useGetTeamMachines,
  useGetTeamStorages,
  useUpdateStorageName,
  useUpdateStorageVault,
} from '@/api/api-hooks.generated';
import { useDropdownData } from '@/api/queries/useDropdownData';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { TooltipButton } from '@/components/common/buttons';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildEditMenuItem,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import { PageHeader } from '@/components/common/PageHeader';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import TeamSelector from '@/components/common/TeamSelector';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import RcloneImportWizard from '@/features/storage/components/RcloneImportWizard';
import {
  useAsyncAction,
  useDialogState,
  usePagination,
  useQueueTraceModal,
  useTraceModal,
  useUnifiedModal,
} from '@/hooks';
import { useQueueAction } from '@/hooks/useQueueAction';
import { useTeamSelection } from '@/hooks/useTeamSelection';
import { showMessage } from '@/utils/messages';
import {
  CloudOutlined,
  FunctionOutlined,
  ImportOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@/utils/optimizedIcons';
import type { GetTeamStorages_ResultSet1 } from '@rediacc/shared/types';
import { useBuildStorageColumns } from './hooks/buildStorageColumns';
import { useStorageHandlers } from './hooks/useStorageHandlers';

const TeamSelectorWrapper = (props: React.ComponentProps<typeof Flex>) => (
  <Flex
    className="w-full"
    // eslint-disable-next-line no-restricted-syntax
    style={{ maxWidth: 360 }}
    {...props}
  />
);

const StoragePage: React.FC = () => {
  const { t } = useTranslation(['resources', 'common']);
  const [modal, contextHolder] = Modal.useModal();

  // Custom hooks for common patterns
  const {
    teams,
    selectedTeam,
    setSelectedTeam,
    isLoading: teamsLoading,
  } = useTeamSelection({
    pageId: 'storage',
  });
  const {
    modalState: unifiedModalState,
    currentResource,
    openModal: openUnifiedModal,
    closeModal: closeUnifiedModal,
    setCurrentResource,
  } = useUnifiedModal<GetTeamStorages_ResultSet1 & Record<string, unknown>>('storage');
  const {
    page: storagePage,
    pageSize: storagePageSize,
    setPage: setStoragePage,
    setPageSize: setStoragePageSize,
  } = usePagination({ defaultPageSize: 15 });

  // Modal state management with new hooks
  const rcloneImportWizard = useDialogState();
  const queueTrace = useQueueTraceModal();
  const auditTrace = useTraceModal();

  // Async action handler
  const { execute } = useAsyncAction();

  // Data fetching
  const {
    data: storages = [],
    isLoading: storagesLoading,
    refetch: refetchStorage,
  } = useGetTeamStorages(selectedTeam ?? undefined);

  const { data: machines = [] } = useGetTeamMachines(selectedTeam ?? undefined);

  const { data: dropdownData } = useDropdownData();
  const { executeDynamic, isExecuting } = useQueueAction();

  // Mutations
  const createStorageMutation = useCreateStorage();
  const updateStorageNameMutation = useUpdateStorageName();
  const deleteStorageMutation = useDeleteStorage();
  const updateStorageVaultMutation = useUpdateStorageVault();

  // Handlers
  const {
    handleDeleteStorage,
    handleUnifiedModalSubmit,
    handleUnifiedVaultUpdate,
    handleStorageFunctionSelected,
  } = useStorageHandlers({
    t,
    modal,
    execute,
    deleteStorageMutation,
    createStorageMutation,
    updateStorageNameMutation,
    updateStorageVaultMutation,
    refetchStorage,
    closeUnifiedModal,
    unifiedModalMode: unifiedModalState.mode,
    currentResource,
    dropdownData,
    machines,
    storages,
    teams: teams.map((t) => ({ ...t, teamName: t.teamName ?? '' })),
    executeDynamic,
    openQueueTrace: queueTrace.open,
  });

  // Columns
  const storageColumns = useBuildStorageColumns({
    t,
    openUnifiedModal,
    setCurrentResource,
    handleDeleteStorage,
    openAuditTrace: auditTrace.open,
  });

  // Mobile render
  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetTeamStorages_ResultSet1) => {
      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(t, () =>
          openUnifiedModal('edit', record as GetTeamStorages_ResultSet1 & Record<string, unknown>)
        ),
        {
          key: 'run',
          label: t('common:actions.runFunction'),
          icon: <FunctionOutlined />,
          onClick: () => {
            setCurrentResource(record as GetTeamStorages_ResultSet1 & Record<string, unknown>);
            openUnifiedModal(
              'create',
              record as GetTeamStorages_ResultSet1 & Record<string, unknown>
            );
          },
        },
        buildTraceMenuItem(t, () =>
          auditTrace.open({
            entityType: 'Storage',
            entityIdentifier: record.storageName ?? '',
            entityName: record.storageName ?? '',
          })
        ),
        buildDivider(),
        buildDeleteMenuItem(t, () => handleDeleteStorage(record)),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <CloudOutlined />
            <Typography.Text strong className="truncate">
              {record.storageName}
            </Typography.Text>
          </Space>
          <Tag>{record.teamName}</Tag>
        </MobileCard>
      );
    },
    [t, openUnifiedModal, setCurrentResource, auditTrace, handleDeleteStorage]
  );

  const isSubmitting = [
    createStorageMutation.isPending,
    updateStorageNameMutation.isPending,
    isExecuting,
  ].some(Boolean);

  const isUpdatingVault = updateStorageVaultMutation.isPending;

  const modalExistingData = unifiedModalState.data ?? currentResource ?? undefined;

  const hasTeamSelection = selectedTeam !== null;
  const displayedStorages = hasTeamSelection ? storages : [];
  const emptyDescription = hasTeamSelection ? t('storage.noStorage') : t('teams.selectTeamPrompt');

  // Show loading when teams are being fetched OR when storages are loading
  const isLoading = teamsLoading || storagesLoading;

  return (
    <>
      <Flex vertical>
        <TeamSelectorWrapper>
          <TeamSelector
            data-testid="resources-team-selector"
            teams={teams}
            selectedTeam={selectedTeam}
            onChange={setSelectedTeam}
            loading={teamsLoading}
            placeholder={t('teams.selectTeamToView')}
          />
        </TeamSelectorWrapper>

        <ResourceListView<GetTeamStorages_ResultSet1>
          title={<PageHeader title={t('storage.title')} subtitle={t('storage.subtitle')} />}
          loading={isLoading}
          data={displayedStorages}
          columns={storageColumns}
          mobileRender={mobileRender}
          rowKey="storageName"
          data-testid="resources-storage-table"
          resourceType="storage locations"
          searchPlaceholder={t('storage.searchStorage')}
          emptyDescription={emptyDescription}
          pagination={
            hasTeamSelection
              ? {
                  current: storagePage,
                  pageSize: storagePageSize,
                  total: displayedStorages.length,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total: number, range: [number, number]) =>
                    `${t('common:general.showingRecords', {
                      start: range[0],
                      end: range[1],
                      total,
                    })}`,
                  onChange: (page: number, size: number) => {
                    setStoragePage(page);
                    if (size && size !== storagePageSize) {
                      setStoragePageSize(size);
                      setStoragePage(1);
                    }
                  },
                  position: ['bottomRight'],
                }
              : false
          }
          actions={
            hasTeamSelection ? (
              <>
                <TooltipButton
                  tooltip={t('storage.createStorage')}
                  type="primary"
                  icon={<PlusOutlined />}
                  data-testid="resources-create-storage-button"
                  onClick={() => openUnifiedModal('create')}
                />
                <TooltipButton
                  tooltip={t('resources:storage.import.button')}
                  icon={<ImportOutlined />}
                  data-testid="resources-import-button"
                  onClick={() => rcloneImportWizard.open()}
                />
                <TooltipButton
                  tooltip={t('common:actions.refresh')}
                  icon={<ReloadOutlined />}
                  data-testid="resources-refresh-button"
                  onClick={() => void refetchStorage()}
                />
              </>
            ) : undefined
          }
        />
      </Flex>

      <UnifiedResourceModal
        data-testid="resources-storage-modal"
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType="storage"
        mode={unifiedModalState.mode}
        existingData={modalExistingData}
        teamFilter={selectedTeam ? [selectedTeam] : undefined}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        onFunctionSubmit={
          unifiedModalState.mode === 'create' ? undefined : handleStorageFunctionSelected
        }
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={['backup']}
        hiddenParams={['storage']}
        defaultParams={currentResource ? { storage: currentResource.storageName ?? '' } : {}}
      />

      <QueueItemTraceModal
        data-testid="resources-queue-trace-modal"
        taskId={queueTrace.state.taskId}
        open={queueTrace.state.open}
        onCancel={() => {
          queueTrace.close();
          void refetchStorage();
        }}
      />

      <AuditTraceModal
        data-testid="resources-audit-trace-modal"
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />

      <RcloneImportWizard
        data-testid="resources-rclone-import-wizard"
        open={rcloneImportWizard.isOpen}
        onClose={rcloneImportWizard.close}
        teamName={selectedTeam ?? ''}
        onImportComplete={() => {
          void refetchStorage();
          showMessage('success', t('resources:storage.import.successMessage'));
        }}
      />

      {contextHolder}
    </>
  );
};

export default StoragePage;
