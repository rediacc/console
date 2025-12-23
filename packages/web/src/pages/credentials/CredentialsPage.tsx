import React, { useCallback, useEffect, useMemo } from 'react';
import { Button, Flex, Space, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { QueueFunction } from '@/api/queries/queue';
import {
  Repository,
  useCreateRepository,
  useDeleteRepository,
  useRepositories,
  useUpdateRepositoryName,
  useUpdateRepositoryVault,
} from '@/api/queries/repositories';
import { useStorage } from '@/api/queries/storage';
import { useDropdownData } from '@/api/queries/useDropdownData';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import ResourceListView from '@/components/common/ResourceListView';
import TeamSelector from '@/components/common/TeamSelector';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import {
  useAsyncAction,
  usePagination,
  useQueueTraceModal,
  useTeamSelection,
  useTraceModal,
  useUnifiedModal,
} from '@/hooks';
import { useQueueAction } from '@/hooks/useQueueAction';
import { useRepositoryCreation } from '@/hooks/useRepositoryCreation';
import { getAffectedResources as coreGetAffectedResources } from '@/platform';
import type { QueueActionParams } from '@/services/queueActionService';
import { showMessage } from '@/utils/messages';
import { PlusOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import { buildRepositoryColumns } from './columns';
import { useDeleteConfirmationModal } from './components/DeleteConfirmationModal';
import { RepositoryMobileCard } from './components/RepositoryMobileCard';

interface CredentialsLocationState {
  createRepository?: boolean;
  selectedTeam?: string;
  selectedMachine?: string;
  selectedTemplate?: string;
}

type RepositoryFormValues = {
  repositoryName?: string;
  vaultContent?: string;
  teamName?: string;
  [key: string]: unknown;
};

type RepoModalData = Partial<Repository> & Record<string, unknown>;

const CredentialsPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common']);
  const location = useLocation();
  const navigate = useNavigate();

  // Use custom hooks for common patterns
  const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection();
  const {
    modalState: unifiedModalState,
    currentResource,
    openModal: openUnifiedModal,
    closeModal: closeUnifiedModal,
  } = useUnifiedModal<Repository & Record<string, unknown>>('repository');
  const {
    page: repositoryPage,
    pageSize: repositoryPageSize,
    setPage: setRepositoryPage,
    setPageSize: setRepositoryPageSize,
  } = usePagination({ defaultPageSize: 15 });

  // Modal state management with new hooks
  const queueTrace = useQueueTraceModal();
  const auditTrace = useTraceModal();

  // Async action handler
  const { execute } = useAsyncAction();

  const { data: dropdownData } = useDropdownData();

  const {
    data: repositories = [],
    isLoading: repositoriesLoading,
    refetch: refetchRepos,
  } = useRepositories(selectedTeams.length > 0 ? selectedTeams : undefined);

  const { data: machines = [] } = useMachines(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    selectedTeams.length > 0
  );

  const { data: storages = [] } = useStorage(selectedTeams.length > 0 ? selectedTeams : undefined);

  const createRepositoryMutation = useCreateRepository();
  const updateRepoNameMutation = useUpdateRepositoryName();
  const deleteRepoMutation = useDeleteRepository();
  const updateRepoVaultMutation = useUpdateRepositoryVault();

  const { createRepository: createRepositoryWithQueue, isCreating } =
    useRepositoryCreation(machines);
  const { executeAction, isExecuting } = useQueueAction();

  const originalRepositories = useMemo(
    () =>
      repositories.filter(
        (repository) => !repository.grandGuid || repository.grandGuid === repository.repositoryGuid
      ),
    [repositories]
  );

  const getAffectedResources = useCallback(
    (repository: Repository) => coreGetAffectedResources(repository, repositories, machines),
    [repositories, machines]
  );

  const { handleDeleteRepository, contextHolder } = useDeleteConfirmationModal({
    t,
    getAffectedResources,
    onDelete: (repository) =>
      deleteRepoMutation.mutateAsync({
        teamName: repository.teamName,
        repositoryName: repository.repositoryName,
      }),
    onDeleted: refetchRepos,
  });

  const handleUnifiedModalSubmit = useCallback(
    async (data: RepositoryFormValues) => {
      await execute(
        async () => {
          if (unifiedModalState.mode === 'create') {
            const result = await createRepositoryWithQueue(
              data as RepositoryFormValues & { repositoryName: string; teamName: string }
            );

            if (result.success) {
              closeUnifiedModal();

              if (result.taskId) {
                queueTrace.open(result.taskId, result.machineName);
              } else {
                refetchRepos();
              }
            } else {
              showMessage('error', result.error || t('repositories.failedToCreateRepository'));
            }
          } else if (currentResource) {
            const currentName = currentResource.repositoryName;
            const newName = data.repositoryName;

            if (newName && newName !== currentName) {
              await updateRepoNameMutation.mutateAsync({
                teamName: currentResource.teamName,
                currentRepositoryName: currentName,
                newRepositoryName: newName,
              });
            }

            const vaultData = data.vaultContent;
            if (vaultData && vaultData !== currentResource.vaultContent) {
              await updateRepoVaultMutation.mutateAsync({
                teamName: currentResource.teamName,
                repositoryName: newName || currentName,
                repositoryTag: currentResource.repositoryTag || 'latest',
                vaultContent: vaultData,
                vaultVersion: currentResource.vaultVersion + 1,
              });
            }

            closeUnifiedModal();
            refetchRepos();
          }
        },
        { skipSuccessMessage: true }
      );
    },
    [
      closeUnifiedModal,
      createRepositoryWithQueue,
      currentResource,
      execute,
      queueTrace,
      refetchRepos,
      t,
      unifiedModalState.mode,
      updateRepoNameMutation,
      updateRepoVaultMutation,
    ]
  );

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
      if (!currentResource) return;
      await execute(
        async () => {
          await updateRepoVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            repositoryName: currentResource.repositoryName,
            repositoryTag: currentResource.repositoryTag || 'latest',
            vaultContent: vault,
            vaultVersion: version,
          });
          refetchRepos();
          closeUnifiedModal();
        },
        { skipSuccessMessage: true }
      );
    },
    [closeUnifiedModal, currentResource, execute, refetchRepos, updateRepoVaultMutation]
  );

  const handleRepoFunctionSelected = useCallback(
    async (functionData: {
      function: QueueFunction;
      params: Record<string, unknown>;
      priority: number;
      description: string;
      selectedMachine?: string;
    }) => {
      if (!currentResource) return;
      try {
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
          addedVia: 'repository-table',
          teamVault:
            teams.find((team) => team.teamName === currentResource.teamName)?.vaultContent || '{}',
          repositoryGuid: currentResource.repositoryGuid,
          vaultContent: currentResource.vaultContent || '{}',
          repositoryNetworkId: currentResource.repositoryNetworkId,
          repositoryNetworkMode: currentResource.repositoryNetworkMode,
          repositoryTag: currentResource.repositoryTag,
          machineVault: selectedMachine?.vaultContent || '{}',
        };

        if (functionData.function.name === 'pull') {
          if (functionData.params.sourceType === 'machine' && functionData.params.from) {
            const sourceMachine = machines.find(
              (machine) => machine.machineName === functionData.params.from
            );
            if (sourceMachine?.vaultContent) {
              queuePayload.sourceMachineVault = sourceMachine.vaultContent;
            }
          }

          if (functionData.params.sourceType === 'storage' && functionData.params.from) {
            const sourceStorage = storages.find(
              (storage) => storage.storageName === functionData.params.from
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
            showMessage('success', t('repositories.queueItemCreated'));
            queueTrace.open(result.taskId, machineEntry.value);
          } else if (result.isQueued) {
            showMessage(
              'info',
              t('resources:messages.highestPriorityQueued', { resourceType: 'repository' })
            );
          }
        } else {
          showMessage('error', result.error || t('resources:errors.failedToCreateQueueItem'));
        }
      } catch {
        showMessage('error', t('resources:errors.failedToCreateQueueItem'));
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
    createRepositoryMutation.isPending ||
    updateRepoNameMutation.isPending ||
    isCreating ||
    isExecuting;

  const isUpdatingVault = updateRepoVaultMutation.isPending;

  useEffect(() => {
    const state = location.state as CredentialsLocationState | null;
    if (state?.createRepository) {
      if (state.selectedTeam) {
        setSelectedTeams([state.selectedTeam]);
      }

      setTimeout(() => {
        const modalData: RepoModalData = {
          teamName: state.selectedTeam,
          machineName: state.selectedMachine,
          preselectedTemplate: state.selectedTemplate,
        };
        openUnifiedModal('create', modalData, 'credentials-only');
      }, 100);

      navigate(location.pathname, { replace: true });
    }
  }, [location, navigate, openUnifiedModal, setSelectedTeams]);

  const repositoryColumns = useMemo(
    () =>
      buildRepositoryColumns({
        t,
        onEdit: (repository) =>
          openUnifiedModal('edit', repository as Repository & Record<string, unknown>),
        onTrace: (repository) =>
          auditTrace.open({
            entityType: 'Repository',
            entityIdentifier: repository.repositoryName,
            entityName: repository.repositoryName,
          }),
        onDelete: handleDeleteRepository,
      }),
    [auditTrace, handleDeleteRepository, openUnifiedModal, t]
  );

  const hasTeamSelection = selectedTeams.length > 0;
  const displayedRepositories = hasTeamSelection ? originalRepositories : [];
  const emptyDescription = hasTeamSelection
    ? t('repositories.noRepositories')
    : t('teams.selectTeamPrompt');

  const mobileRender = useCallback(
    (record: Repository) => (
      <RepositoryMobileCard
        record={record}
        t={t}
        onEdit={(repository) =>
          openUnifiedModal('edit', repository as Repository & Record<string, unknown>)
        }
        onTrace={(repository) =>
          auditTrace.open({
            entityType: 'Repository',
            entityIdentifier: repository.repositoryName,
            entityName: repository.repositoryName,
          })
        }
        onDelete={handleDeleteRepository}
      />
    ),
    [t, openUnifiedModal, auditTrace, handleDeleteRepository]
  );

  return (
    <>
      <Flex vertical>
        <Flex vertical>
          {/* eslint-disable-next-line no-restricted-syntax */}
          <Flex style={{ width: '100%', maxWidth: 360 }}>
            <TeamSelector
              data-testid="resources-team-selector"
              teams={teams}
              selectedTeams={selectedTeams}
              onChange={setSelectedTeams}
              loading={teamsLoading}
              placeholder={t('teams.selectTeamToView')}
            />
          </Flex>

          <ResourceListView<Repository>
            title={
              <Space direction="vertical" size={0}>
                <Typography.Text strong>{t('credentials.title')}</Typography.Text>
                <Typography.Text>{t('credentials.subtitle')}</Typography.Text>
              </Space>
            }
            loading={repositoriesLoading}
            data={displayedRepositories}
            columns={repositoryColumns}
            mobileRender={mobileRender}
            rowKey="repositoryGuid"
            data-testid="resources-repository-table"
            resourceType="repositories"
            emptyDescription={emptyDescription}
            pagination={
              hasTeamSelection
                ? {
                    current: repositoryPage,
                    pageSize: repositoryPageSize,
                    total: displayedRepositories.length,
                    showSizeChanger: true,
                    pageSizeOptions: ['10', '20', '50', '100'],
                    showTotal: (total: number, range: [number, number]) =>
                      `${t('common:general.showingRecords', {
                        start: range[0],
                        end: range[1],
                        total,
                      })}`,
                    onChange: (page: number, size: number) => {
                      setRepositoryPage(page);
                      if (size && size !== repositoryPageSize) {
                        setRepositoryPageSize(size);
                        setRepositoryPage(1);
                      }
                    },
                    position: ['bottomRight'],
                  }
                : false
            }
            actions={
              hasTeamSelection ? (
                <>
                  <Tooltip title={t('repositories.createRepository')}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      data-testid="resources-create-repositorie-button"
                      onClick={() => openUnifiedModal('create', undefined, 'credentials-only')}
                      aria-label={t('repositories.createRepository')}
                    />
                  </Tooltip>
                  <Tooltip title={t('common:actions.refresh')}>
                    <Button
                      icon={<ReloadOutlined />}
                      data-testid="resources-refresh-button"
                      onClick={() => refetchRepos()}
                      aria-label={t('common:actions.refresh')}
                    />
                  </Tooltip>
                </>
              ) : undefined
            }
          />
        </Flex>
      </Flex>

      <UnifiedResourceModal
        data-testid="resources-repository-modal"
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType="repository"
        mode={unifiedModalState.mode}
        existingData={(unifiedModalState.data || currentResource) as RepoModalData | undefined}
        teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        creationContext={unifiedModalState.creationContext}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        onFunctionSubmit={
          unifiedModalState.mode === 'create' ? undefined : handleRepoFunctionSelected
        }
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={['repository', 'backup', 'network']}
        hiddenParams={['repository', 'grand']}
        defaultParams={
          currentResource
            ? {
                repository: currentResource.repositoryGuid,
                repositoryName: currentResource.repositoryName,
                grand: currentResource.grandGuid || '',
              }
            : {}
        }
      />

      <QueueItemTraceModal
        data-testid="resources-queue-trace-modal"
        taskId={queueTrace.state.taskId}
        open={queueTrace.state.open}
        onCancel={() => {
          queueTrace.close();
          refetchRepos();
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

      {contextHolder}
    </>
  );
};

export default CredentialsPage;
