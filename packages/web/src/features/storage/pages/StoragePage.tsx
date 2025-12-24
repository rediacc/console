import React from 'react';
import { Button, Flex, Modal, Space, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useMachines } from '@/api/queries/machines';
import {
  GetTeamStorages_ResultSet1,
  useCreateStorage,
  useDeleteStorage,
  useStorage,
  useUpdateStorageName,
  useUpdateStorageVault,
} from '@/api/queries/storage';
import { useDropdownData } from '@/api/queries/useDropdownData';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
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
import { ImportOutlined, PlusOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import { useStorageColumns } from './hooks/useStorageColumns';
import { useStorageHandlers } from './hooks/useStorageHandlers';
import { useStorageMobileRender } from './hooks/useStorageMobileRender';

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
  const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection();
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
  } = useStorage(selectedTeams.length > 0 ? selectedTeams : undefined);

  const { data: machines = [] } = useMachines(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    selectedTeams.length > 0
  );

  const { data: dropdownData } = useDropdownData();
  const { executeAction, isExecuting } = useQueueAction();

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
    teams,
    executeAction,
    openQueueTrace: queueTrace.open,
  });

  // Columns
  const storageColumns = useStorageColumns({
    t,
    openUnifiedModal,
    setCurrentResource,
    handleDeleteStorage,
    openAuditTrace: auditTrace.open,
  });

  // Mobile render
  const mobileRender = useStorageMobileRender({
    t,
    openUnifiedModal,
    setCurrentResource,
    handleDeleteStorage,
    openAuditTrace: auditTrace.open,
  });

  const isSubmitting =
    createStorageMutation.isPending || updateStorageNameMutation.isPending || isExecuting;

  const isUpdatingVault = updateStorageVaultMutation.isPending;

  const modalExistingData = unifiedModalState.data ?? currentResource ?? undefined;

  const hasTeamSelection = selectedTeams.length > 0;
  const displayedStorages = hasTeamSelection ? storages : [];
  const emptyDescription = hasTeamSelection ? t('storage.noStorage') : t('teams.selectTeamPrompt');

  return (
    <>
      <Flex vertical>
        <TeamSelectorWrapper>
          <TeamSelector
            data-testid="resources-team-selector"
            teams={teams}
            selectedTeams={selectedTeams}
            onChange={setSelectedTeams}
            loading={teamsLoading}
            placeholder={t('teams.selectTeamToView')}
          />
        </TeamSelectorWrapper>

        <ResourceListView<GetTeamStorages_ResultSet1>
          title={
            <Space direction="vertical" size={0}>
              <Typography.Text strong>{t('storage.title')}</Typography.Text>
              <Typography.Text>{t('storage.subtitle')}</Typography.Text>
            </Space>
          }
          loading={storagesLoading}
          data={displayedStorages}
          columns={storageColumns}
          mobileRender={mobileRender}
          rowKey="storageName"
          data-testid="resources-storage-table"
          resourceType="storage locations"
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
                <Tooltip title={t('storage.createStorage')}>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    data-testid="resources-create-storage-button"
                    onClick={() => openUnifiedModal('create')}
                    aria-label={t('storage.createStorage')}
                  />
                </Tooltip>
                <Tooltip title={t('resources:storage.import.button')}>
                  <Button
                    icon={<ImportOutlined />}
                    data-testid="resources-import-button"
                    onClick={() => rcloneImportWizard.open()}
                    aria-label={t('resources:storage.import.button')}
                  />
                </Tooltip>
                <Tooltip title={t('common:actions.refresh')}>
                  <Button
                    icon={<ReloadOutlined />}
                    data-testid="resources-refresh-button"
                    onClick={() => refetchStorage()}
                    aria-label={t('common:actions.refresh')}
                  />
                </Tooltip>
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
        teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        onFunctionSubmit={
          unifiedModalState.mode === 'create' ? undefined : handleStorageFunctionSelected
        }
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={['backup']}
        hiddenParams={['storage']}
        defaultParams={currentResource ? { storage: currentResource.storageName } : {}}
      />

      <QueueItemTraceModal
        data-testid="resources-queue-trace-modal"
        taskId={queueTrace.state.taskId}
        open={queueTrace.state.open}
        onCancel={() => {
          queueTrace.close();
          refetchStorage();
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
        teamName={selectedTeams[0] || ''}
        onImportComplete={() => {
          refetchStorage();
          showMessage('success', t('resources:storage.import.successMessage'));
        }}
      />

      {contextHolder}
    </>
  );
};

export default StoragePage;
