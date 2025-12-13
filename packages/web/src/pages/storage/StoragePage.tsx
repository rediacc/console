import React, { useCallback, useMemo } from 'react';
import { Modal, Space, Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import styled, { useTheme } from 'styled-components';
import { useMachines } from '@/api/queries/machines';
import { QueueFunction } from '@/api/queries/queue';
import {
  GetTeamStorages_ResultSet1,
  useCreateStorage,
  useDeleteStorage,
  useStorage,
  useUpdateStorageName,
  useUpdateStorageVault,
} from '@/api/queries/storage';
import { useDropdownData } from '@/api/queries/useDropdownData';
import { ActionButtonConfig, ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { createActionColumn } from '@/components/common/columns';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import ResourceListView, {
  COLUMN_RESPONSIVE,
  COLUMN_WIDTHS,
} from '@/components/common/ResourceListView';
import TeamSelector from '@/components/common/TeamSelector';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import {
  ListSubtitle,
  ListTitle,
  ListTitleRow,
  PageWrapper,
  RediaccButton,
  SectionHeading,
  SectionStack,
} from '@/components/ui';
import { featureFlags } from '@/config/featureFlags';
import {
  useAsyncAction,
  useDialogState,
  usePagination,
  useQueueTraceModal,
  useTeamSelection,
  useTraceModal,
  useUnifiedModal,
} from '@/hooks';
import { useQueueAction } from '@/hooks/useQueueAction';
import RcloneImportWizard from '@/pages/storage/components/RcloneImportWizard';
import type { QueueActionParams } from '@/services/queueActionService';
import { confirmDelete } from '@/utils/confirmations';
import { showMessage } from '@/utils/messages';
import {
  CloudOutlined,
  DeleteOutlined,
  EditOutlined,
  FunctionOutlined,
  HistoryOutlined,
  ImportOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@/utils/optimizedIcons';
import type { StorageFormValues } from '@rediacc/shared/types';

interface StorageFunctionData {
  function: QueueFunction;
  params: Record<string, string | number | string[] | undefined>;
  priority: number;
  description: string;
  selectedMachine?: string;
}

const TeamSelectorWrapper = styled.div`
  width: 100%;
  max-width: ${({ theme }) => theme.dimensions.SELECTOR_MAX_WIDTH}px;
`;

const StorageLocationIcon = styled(CloudOutlined)`
  color: ${({ theme }) => theme.colors.primary};
`;

const StoragePage: React.FC = () => {
  const { t } = useTranslation(['resources', 'common']);
  const theme = useTheme();
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

  const handleDeleteStorage = useCallback(
    (storage: GetTeamStorages_ResultSet1) => {
      confirmDelete({
        modal,
        t,
        resourceType: 'storage',
        resourceName: storage.storageName,
        translationNamespace: 'storage',
        onConfirm: () =>
          deleteStorageMutation.mutateAsync({
            teamName: storage.teamName,
            storageName: storage.storageName,
          }),
        onSuccess: () => refetchStorage(),
      });
    },
    [deleteStorageMutation, modal, refetchStorage, t]
  );

  const handleUnifiedModalSubmit = useCallback(
    async (data: Record<string, unknown>) => {
      const storageData = data as StorageFormValues;
      await execute(
        async () => {
          if (unifiedModalState.mode === 'create') {
            await createStorageMutation.mutateAsync(storageData);
          } else if (currentResource) {
            const currentName = currentResource.storageName;
            const newName = storageData.storageName;

            if (newName && newName !== currentName) {
              await updateStorageNameMutation.mutateAsync({
                teamName: currentResource.teamName,
                currentStorageName: currentName,
                newStorageName: newName,
              });
            }

            const vaultData = storageData.vaultContent;
            if (vaultData && vaultData !== currentResource.vaultContent) {
              await updateStorageVaultMutation.mutateAsync({
                teamName: currentResource.teamName,
                storageName: newName || currentName,
                vaultContent: vaultData,
                vaultVersion: currentResource.vaultVersion + 1,
              });
            }
          }
          closeUnifiedModal();
          refetchStorage();
        },
        { skipSuccessMessage: true }
      );
    },
    [
      closeUnifiedModal,
      createStorageMutation,
      currentResource,
      execute,
      refetchStorage,
      unifiedModalState.mode,
      updateStorageNameMutation,
      updateStorageVaultMutation,
    ]
  );

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
      if (!currentResource) return;
      await execute(
        async () => {
          await updateStorageVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            storageName: currentResource.storageName,
            vaultContent: vault,
            vaultVersion: version,
          });
          refetchStorage();
          closeUnifiedModal();
        },
        { skipSuccessMessage: true }
      );
    },
    [closeUnifiedModal, currentResource, execute, refetchStorage, updateStorageVaultMutation]
  );

  const handleStorageFunctionSelected = useCallback(
    async (functionData: StorageFunctionData) => {
      if (!currentResource) return;

      if (!functionData.selectedMachine) {
        showMessage('error', t('resources:errors.machineNotFound'));
        return;
      }

      const teamEntry = dropdownData?.machinesByTeam?.find(
        (team) => team.teamName === currentResource.teamName
      );
      const machineEntry = teamEntry?.machines?.find(
        (machine) => machine.value === functionData.selectedMachine
      );

      if (!machineEntry) {
        showMessage('error', t('resources:errors.machineNotFound'));
        return;
      }

      const selectedMachine = machines.find(
        (machine) =>
          machine.machineName === machineEntry.value &&
          machine.teamName === currentResource.teamName
      );

      const queuePayload: QueueActionParams = {
        teamName: currentResource.teamName,
        machineName: machineEntry.value,
        bridgeName: machineEntry.bridgeName,
        functionName: functionData.function.name,
        params: functionData.params,
        priority: functionData.priority,
        description: functionData.description,
        addedVia: 'storage-table',
        teamVault:
          teams.find((team) => team.teamName === currentResource.teamName)?.vaultContent || '{}',
        storageName: currentResource.storageName,
        storageVault: currentResource.vaultContent || '{}',
        machineVault: selectedMachine?.vaultContent || '{}',
      };

      // Handle pull function source vaults
      if (functionData.function.name === 'pull') {
        const sourceType = functionData.params.sourceType;
        const sourceIdentifier = functionData.params.from;

        if (sourceType === 'machine' && typeof sourceIdentifier === 'string') {
          const sourceMachine = machines.find(
            (machine) => machine.machineName === sourceIdentifier
          );
          if (sourceMachine?.vaultContent) {
            queuePayload.sourceMachineVault = sourceMachine.vaultContent;
          }
        }

        if (sourceType === 'storage' && typeof sourceIdentifier === 'string') {
          const sourceStorage = storages.find(
            (storage) => storage.storageName === sourceIdentifier
          );
          if (sourceStorage?.vaultContent) {
            queuePayload.sourceStorageVault = sourceStorage.vaultContent;
          }
        }
      }

      const result = await executeAction(queuePayload);
      closeUnifiedModal();

      if (result.success) {
        if (result.taskId) {
          showMessage('success', t('storage.queueItemCreated'));
          queueTrace.open(result.taskId, machineEntry.value);
        } else if (result.isQueued) {
          showMessage(
            'info',
            t('resources:messages.highestPriorityQueued', { resourceType: 'storage' })
          );
        }
      } else {
        showMessage('error', result.error || t('resources:errors.failedToCreateQueueItem'));
      }
    },
    [
      closeUnifiedModal,
      currentResource,
      dropdownData,
      executeAction,
      machines,
      queueTrace,
      storages,
      t,
      teams,
    ]
  );

  const isSubmitting =
    createStorageMutation.isPending || updateStorageNameMutation.isPending || isExecuting;

  const isUpdatingVault = updateStorageVaultMutation.isPending;

  const modalExistingData = unifiedModalState.data ?? currentResource ?? undefined;

  const storageColumns = useMemo(
    () => [
      {
        title: t('storage.storageName'),
        dataIndex: 'storageName',
        key: 'storageName',
        width: COLUMN_WIDTHS.NAME,
        ellipsis: true,
        render: (text: string) => (
          <Space>
            <StorageLocationIcon />
            <strong>{text}</strong>
          </Space>
        ),
      },
      {
        title: t('general.team'),
        dataIndex: 'teamName',
        key: 'teamName',
        width: COLUMN_WIDTHS.TAG,
        ellipsis: true,
        render: (teamName: string) => <Tag color={theme.colors.secondary}>{teamName}</Tag>,
      },
      ...(featureFlags.isEnabled('vaultVersionColumns')
        ? [
            {
              title: t('general.vaultVersion'),
              dataIndex: 'vaultVersion',
              key: 'vaultVersion',
              width: COLUMN_WIDTHS.VERSION,
              align: 'center' as const,
              responsive: COLUMN_RESPONSIVE.DESKTOP_ONLY,
              render: (version: number) => (
                <Tag>{t('common:general.versionFormat', { version })}</Tag>
              ),
            },
          ]
        : []),
      createActionColumn<GetTeamStorages_ResultSet1>({
        width: COLUMN_WIDTHS.ACTIONS_WIDE,
        renderActions: (record) => {
          const buttons: ActionButtonConfig<GetTeamStorages_ResultSet1>[] = [
            {
              type: 'edit',
              icon: <EditOutlined />,
              tooltip: 'common:actions.edit',
              onClick: (r: GetTeamStorages_ResultSet1) =>
                openUnifiedModal('edit', r as GetTeamStorages_ResultSet1 & Record<string, unknown>),
              variant: 'primary',
            },
            {
              type: 'run',
              icon: <FunctionOutlined />,
              tooltip: 'common:actions.runFunction',
              onClick: (r: GetTeamStorages_ResultSet1) => {
                setCurrentResource(r as GetTeamStorages_ResultSet1 & Record<string, unknown>);
                openUnifiedModal(
                  'create',
                  r as GetTeamStorages_ResultSet1 & Record<string, unknown>
                );
              },
              variant: 'primary',
            },
            {
              type: 'trace',
              icon: <HistoryOutlined />,
              tooltip: 'machines:trace',
              onClick: (r: GetTeamStorages_ResultSet1) =>
                auditTrace.open({
                  entityType: 'Storage',
                  entityIdentifier: r.storageName,
                  entityName: r.storageName,
                }),
              variant: 'default',
            },
            {
              type: 'delete',
              icon: <DeleteOutlined />,
              tooltip: 'common:actions.delete',
              onClick: handleDeleteStorage,
              variant: 'primary',
              danger: true,
            },
          ];

          return (
            <ActionButtonGroup<GetTeamStorages_ResultSet1>
              buttons={buttons}
              record={record}
              idField="storageName"
              testIdPrefix="resources-storage"
              t={t}
            />
          );
        },
      }),
    ],
    [
      auditTrace,
      handleDeleteStorage,
      openUnifiedModal,
      setCurrentResource,
      t,
      theme.colors.secondary,
    ]
  );

  const hasTeamSelection = selectedTeams.length > 0;
  const displayedStorages = hasTeamSelection ? storages : [];
  const emptyDescription = hasTeamSelection
    ? t('storage.noStorage', { defaultValue: 'No storage found in this team' })
    : t('teams.selectTeamPrompt', { defaultValue: 'Select a team to view its resources' });

  return (
    <>
      <PageWrapper>
        <SectionStack>
          <SectionHeading level={3}>
            {t('storage.heading', { defaultValue: 'Storage' })}
          </SectionHeading>

          <TeamSelectorWrapper>
            <TeamSelector
              data-testid="resources-team-selector"
              teams={teams}
              selectedTeams={selectedTeams}
              onChange={setSelectedTeams}
              loading={teamsLoading}
              placeholder={t('teams.selectTeamToView', {
                defaultValue: 'Select a team to view its resources',
              })}
            />
          </TeamSelectorWrapper>

          <ResourceListView<GetTeamStorages_ResultSet1>
            title={
              <ListTitleRow>
                <ListTitle>{t('storage.title', { defaultValue: 'Storage Locations' })}</ListTitle>
                <ListSubtitle>
                  {t('storage.subtitle', {
                    defaultValue: 'Manage remote storage locations and rclone configurations',
                  })}
                </ListSubtitle>
              </ListTitleRow>
            }
            loading={storagesLoading}
            data={displayedStorages}
            columns={storageColumns}
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
                    <RediaccButton
                      variant="primary"
                      icon={<PlusOutlined />}
                      data-testid="resources-create-storage-button"
                      onClick={() => openUnifiedModal('create')}
                      aria-label={t('storage.createStorage')}
                    />
                  </Tooltip>
                  <Tooltip title={t('resources:storage.import.button')}>
                    <RediaccButton
                      icon={<ImportOutlined />}
                      data-testid="resources-import-button"
                      onClick={() => rcloneImportWizard.open()}
                      aria-label={t('resources:storage.import.button')}
                    />
                  </Tooltip>
                  <Tooltip title={t('common:actions.refresh')}>
                    <RediaccButton
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
        </SectionStack>
      </PageWrapper>

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
