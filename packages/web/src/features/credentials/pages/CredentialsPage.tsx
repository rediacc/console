import React, { useCallback, useEffect, useMemo } from 'react';
import { Flex } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  useCreateRepository,
  useDeleteRepository,
  useUpdateRepositoryName,
  useUpdateRepositoryVault,
} from '@/api/api-hooks.generated';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { TooltipButton } from '@/components/common/buttons';
import { buildRepositoryColumns } from '@/components/common/columns/builders/credentialColumns';
import { PageHeader } from '@/components/common/PageHeader';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import ResourceListView from '@/components/common/ResourceListView';
import TeamSelector from '@/components/common/TeamSelector';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import {
  useAsyncAction,
  usePagination,
  useQueueTraceModal,
  useTraceModal,
  useUnifiedModal,
} from '@/hooks';
import { useQueueAction } from '@/hooks/useQueueAction';
import { useRepositoryCreation } from '@/hooks/useRepositoryCreation';
import { useTeamSelection } from '@/hooks/useTeamSelection';
import { getAffectedResources as coreGetAffectedResources } from '@/platform';
import { showMessage } from '@/utils/messages';
import { PlusOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import { DEFAULTS } from '@rediacc/shared/config';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import type { GetTeamRepositories_ResultSet1, QueueFunction } from '@rediacc/shared/types';
import { useDeleteConfirmationModal } from '../components/DeleteConfirmationModal';
import { RepositoryMobileCard } from './components/RepositoryMobileCard';
import { addBackupPullVaults, buildQueuePayload } from './helpers/credentialsHelpers';
import { useCredentialsData } from './hooks/useCredentialsData';

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

type RepoModalData = Partial<GetTeamRepositories_ResultSet1> & Record<string, unknown>;

const CredentialsPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common']);
  const location = useLocation();
  const navigate = useNavigate();

  const {
    teams,
    selectedTeam,
    setSelectedTeam,
    isLoading: teamsLoading,
  } = useTeamSelection({
    pageId: 'credentials',
  });
  const {
    modalState: unifiedModalState,
    currentResource,
    openModal: openUnifiedModal,
    closeModal: closeUnifiedModal,
  } = useUnifiedModal<GetTeamRepositories_ResultSet1 & Record<string, unknown>>('repository');
  const {
    page: repositoryPage,
    pageSize: repositoryPageSize,
    setPage: setRepositoryPage,
    setPageSize: setRepositoryPageSize,
  } = usePagination({ defaultPageSize: 15 });
  const queueTrace = useQueueTraceModal();
  const auditTrace = useTraceModal();
  const { execute } = useAsyncAction();

  const { dropdownData, repositories, repositoriesLoading, refetchRepos, machines, storages } =
    useCredentialsData(selectedTeam);

  const createRepositoryMutation = useCreateRepository();
  const updateRepoNameMutation = useUpdateRepositoryName();
  const deleteRepoMutation = useDeleteRepository();
  const updateRepoVaultMutation = useUpdateRepositoryVault();
  const { createRepository: createRepositoryWithQueue, isCreating } =
    useRepositoryCreation(machines);
  const { executeDynamic, isExecuting } = useQueueAction();

  const originalRepositories = useMemo(
    () =>
      repositories.filter(
        (repository) => !repository.grandGuid || repository.grandGuid === repository.repositoryGuid
      ),
    [repositories]
  );

  const getAffectedResources = useCallback(
    (repository: GetTeamRepositories_ResultSet1) =>
      coreGetAffectedResources(repository, repositories, machines),
    [repositories, machines]
  );

  const { handleDeleteRepository, contextHolder } = useDeleteConfirmationModal({
    t,
    getAffectedResources,
    onDelete: (repository) =>
      deleteRepoMutation.mutateAsync({
        teamName: repository.teamName ?? '',
        repositoryName: repository.repositoryName ?? '',
      }),
    onDeleted: refetchRepos,
  });

  const handleCreateSubmit = useCallback(
    async (data: RepositoryFormValues) => {
      const result = await createRepositoryWithQueue(
        data as RepositoryFormValues & { repositoryName: string; teamName: string }
      );

      if (!result.success) {
        showMessage('error', result.error ?? t('repositories.failedToCreateRepository'));
        return;
      }

      closeUnifiedModal();
      if (result.taskId) {
        queueTrace.open(result.taskId, result.machineName);
      } else {
        void refetchRepos();
      }
    },
    [closeUnifiedModal, createRepositoryWithQueue, queueTrace, refetchRepos, t]
  );

  const handleEditSubmit = useCallback(
    async (data: RepositoryFormValues) => {
      if (!currentResource) return;

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
          repositoryName: newName ?? currentName,
          repositoryTag: currentResource.repositoryTag ?? DEFAULTS.REPOSITORY.TAG,
          vaultContent: vaultData,
          vaultVersion: (currentResource.vaultVersion ?? 0) + 1,
        });
      }

      closeUnifiedModal();
      void refetchRepos();
    },
    [
      closeUnifiedModal,
      currentResource,
      refetchRepos,
      updateRepoNameMutation,
      updateRepoVaultMutation,
    ]
  );

  const handleUnifiedModalSubmit = useCallback(
    async (data: RepositoryFormValues) => {
      await execute(
        async () => {
          if (unifiedModalState.mode === 'create') {
            await handleCreateSubmit(data);
          } else {
            await handleEditSubmit(data);
          }
        },
        { skipSuccessMessage: true }
      );
    },
    [execute, handleCreateSubmit, handleEditSubmit, unifiedModalState.mode]
  );

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
      if (!currentResource) return;
      await execute(
        async () => {
          await updateRepoVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            repositoryName: currentResource.repositoryName,
            repositoryTag: currentResource.repositoryTag ?? DEFAULTS.REPOSITORY.TAG,
            vaultContent: vault,
            vaultVersion: version,
          });
          void refetchRepos();
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
      if (!currentResource || !functionData.selectedMachine) {
        showMessage('error', t('resources:errors.machineNotFound'));
        return;
      }

      try {
        const teamEntry = dropdownData?.machinesByTeam.find(
          (team) => team.teamName === currentResource.teamName
        );
        const machineEntry = teamEntry?.machines.find(
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

        const queuePayload = buildQueuePayload(
          functionData,
          machineEntry,
          selectedMachine,
          currentResource,
          teams
        );
        if (!queuePayload) return;

        if (functionData.function.name === 'backup_pull') {
          addBackupPullVaults(queuePayload, functionData.params, machines, storages);
        }

        const result = await executeDynamic(
          functionData.function.name as BridgeFunctionName,
          queuePayload
        );
        closeUnifiedModal();

        if (!result.success) {
          showMessage('error', result.error ?? t('resources:errors.failedToCreateQueueItem'));
          return;
        }

        if (result.taskId) {
          showMessage('success', t('repositories.queueItemCreated'));
          queueTrace.open(result.taskId, machineEntry.value);
        } else if (result.isQueued) {
          showMessage(
            'info',
            t('resources:messages.highestPriorityQueued', { resourceType: 'repository' })
          );
        }
      } catch {
        showMessage('error', t('resources:errors.failedToCreateQueueItem'));
      }
    },
    [
      closeUnifiedModal,
      currentResource,
      dropdownData,
      executeDynamic,
      machines,
      storages,
      teams,
      queueTrace,
      t,
    ]
  );

  const isSubmitting = [
    createRepositoryMutation.isPending,
    updateRepoNameMutation.isPending,
    isCreating,
    isExecuting,
  ].some(Boolean);

  const isUpdatingVault = updateRepoVaultMutation.isPending;

  useEffect(() => {
    const state = location.state as CredentialsLocationState | null;
    if (!state?.createRepository) return;

    if (state.selectedTeam) {
      setSelectedTeam(state.selectedTeam);
    }

    setTimeout(() => {
      const modalData: RepoModalData = {
        teamName: state.selectedTeam,
        machineName: state.selectedMachine,
        preselectedTemplate: state.selectedTemplate,
      };
      openUnifiedModal('create', modalData, 'credentials-only');
    }, 100);

    void navigate(location.pathname, { replace: true });
  }, [location, navigate, openUnifiedModal, setSelectedTeam]);

  const repositoryColumns = useMemo(
    () =>
      buildRepositoryColumns({
        t,
        onEdit: (repository) =>
          openUnifiedModal(
            'edit',
            repository as GetTeamRepositories_ResultSet1 & Record<string, unknown>
          ),
        onTrace: (repository) =>
          auditTrace.open({
            entityType: 'Repository',
            entityIdentifier: repository.repositoryName ?? '',
            entityName: repository.repositoryName ?? '',
          }),
        onDelete: handleDeleteRepository,
      }),
    [auditTrace, handleDeleteRepository, openUnifiedModal, t]
  );

  const hasTeamSelection = selectedTeam !== null;
  const displayedRepositories = hasTeamSelection ? originalRepositories : [];
  const emptyDescription = hasTeamSelection
    ? t('repositories.noRepositories')
    : t('teams.selectTeamPrompt');

  // Show loading when teams are being fetched OR when repositories are loading
  const isLoading = teamsLoading || repositoriesLoading;

  const mobileRender = useCallback(
    (record: GetTeamRepositories_ResultSet1) => (
      <RepositoryMobileCard
        record={record}
        t={t}
        onEdit={openUnifiedModal.bind(null, 'edit')}
        onTrace={auditTrace.open}
        onDelete={handleDeleteRepository}
      />
    ),
    [t, openUnifiedModal, auditTrace, handleDeleteRepository]
  );

  return (
    <>
      <Flex vertical>
        <Flex vertical>
          <Flex className="w-full-max-sm">
            <TeamSelector
              data-testid="resources-team-selector"
              teams={teams}
              selectedTeam={selectedTeam}
              onChange={setSelectedTeam}
              loading={teamsLoading}
              placeholder={t('teams.selectTeamToView')}
            />
          </Flex>

          <ResourceListView<GetTeamRepositories_ResultSet1>
            title={
              <PageHeader title={t('credentials.title')} subtitle={t('credentials.subtitle')} />
            }
            loading={isLoading}
            data={displayedRepositories}
            columns={repositoryColumns}
            mobileRender={mobileRender}
            rowKey="repositoryGuid"
            data-testid="resources-repository-table"
            resourceType="repositories"
            searchPlaceholder={t('repositories.searchRepositories')}
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
                  <TooltipButton
                    tooltip={t('repositories.createRepository')}
                    type="primary"
                    icon={<PlusOutlined />}
                    data-testid="resources-create-repositorie-button"
                    onClick={() => openUnifiedModal('create', undefined, 'credentials-only')}
                  />
                  <TooltipButton
                    tooltip={t('common:actions.refresh')}
                    icon={<ReloadOutlined />}
                    data-testid="resources-refresh-button"
                    onClick={() => refetchRepos()}
                  />
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
        existingData={(unifiedModalState.data ?? currentResource) as RepoModalData | undefined}
        teamFilter={selectedTeam ? [selectedTeam] : undefined}
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
                repository: currentResource.repositoryGuid ?? '',
                repositoryName: currentResource.repositoryName ?? '',
                grand: currentResource.grandGuid ?? '',
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
          void refetchRepos();
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
