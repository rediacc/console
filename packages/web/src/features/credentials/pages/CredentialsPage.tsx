import React, { useCallback, useEffect, useMemo } from 'react';
import { Flex, Space, Tag, Typography, type MenuProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  useCreateRepository,
  useDeleteRepository,
  useGetTeamMachines,
  useGetTeamRepositories,
  useGetTeamStorages,
  useUpdateRepositoryName,
  useUpdateRepositoryVault,
} from '@/api/api-hooks.generated';
import { useDropdownData } from '@/api/queries/useDropdownData';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { TooltipButton } from '@/components/common/buttons';
import { buildRepositoryColumns } from '@/components/common/columns/builders/credentialColumns';
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
import type { DynamicQueueActionParams } from '@/services/queue';
import { showMessage } from '@/utils/messages';
import { InboxOutlined, PlusOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import type { QueueFunction } from '@rediacc/shared/types';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import { useDeleteConfirmationModal } from '../components/DeleteConfirmationModal';

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

  // Use custom hooks for common patterns
  const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection();
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
  } = useGetTeamRepositories(selectedTeams.length > 0 ? selectedTeams[0] : undefined);

  const { data: machines = [] } = useGetTeamMachines(
    selectedTeams.length > 0 ? selectedTeams[0] : undefined
  );

  const { data: storages = [] } = useGetTeamStorages(
    selectedTeams.length > 0 ? selectedTeams[0] : undefined
  );

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
                void refetchRepos();
              }
            } else {
              showMessage('error', result.error ?? t('repositories.failedToCreateRepository'));
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
                repositoryName: newName ?? currentName,
                repositoryTag: currentResource.repositoryTag ?? 'latest',
                vaultContent: vaultData,
                vaultVersion: (currentResource.vaultVersion ?? 0) + 1,
              });
            }

            closeUnifiedModal();
            void refetchRepos();
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
            repositoryTag: currentResource.repositoryTag ?? 'latest',
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
      if (!currentResource) return;
      try {
        if (!functionData.selectedMachine) {
          showMessage('error', t('resources:errors.machineNotFound'));
          return;
        }

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

        const queuePayload: Omit<DynamicQueueActionParams, 'functionName'> = {
          params: functionData.params,
          teamName: currentResource.teamName ?? '',
          machineName: machineEntry.value,
          bridgeName: machineEntry.bridgeName ?? '',
          priority: functionData.priority,
          description: functionData.description,
          addedVia: 'repository-table',
          teamVault:
            teams.find((team) => team.teamName === currentResource.teamName)?.vaultContent ?? '{}',
          repositoryGuid: currentResource.repositoryGuid ?? undefined,
          vaultContent: currentResource.vaultContent ?? '{}',
          repositoryNetworkId: currentResource.repositoryNetworkId ?? undefined,
          repositoryNetworkMode: currentResource.repositoryNetworkMode ?? undefined,
          repositoryTag: currentResource.repositoryTag ?? undefined,
          machineVault: selectedMachine?.vaultContent ?? '{}',
        };

        if (functionData.function.name === 'backup_pull') {
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

        const result = await executeDynamic(
          functionData.function.name as BridgeFunctionName,
          queuePayload
        );
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
          showMessage('error', result.error ?? t('resources:errors.failedToCreateQueueItem'));
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
      queueTrace,
      storages,
      t,
      teams,
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

      void navigate(location.pathname, { replace: true });
    }
  }, [location, navigate, openUnifiedModal, setSelectedTeams]);

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

  const hasTeamSelection = selectedTeams.length > 0;
  const displayedRepositories = hasTeamSelection ? originalRepositories : [];
  const emptyDescription = hasTeamSelection
    ? t('repositories.noRepositories')
    : t('teams.selectTeamPrompt');

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetTeamRepositories_ResultSet1) => {
      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(t, () =>
          openUnifiedModal(
            'edit',
            record as GetTeamRepositories_ResultSet1 & Record<string, unknown>
          )
        ),
        buildTraceMenuItem(t, () =>
          auditTrace.open({
            entityType: 'Repository',
            entityIdentifier: record.repositoryName ?? '',
            entityName: record.repositoryName ?? '',
          })
        ),
        buildDivider(),
        buildDeleteMenuItem(t, () => handleDeleteRepository(record)),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <InboxOutlined />
            <Typography.Text strong className="truncate">
              {record.repositoryName}
            </Typography.Text>
          </Space>
          <Tag>{record.teamName}</Tag>
        </MobileCard>
      );
    },
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
              selectedTeams={selectedTeams}
              onChange={setSelectedTeams}
              loading={teamsLoading}
              placeholder={t('teams.selectTeamToView')}
            />
          </Flex>

          <ResourceListView<GetTeamRepositories_ResultSet1>
            title={
              <PageHeader title={t('credentials.title')} subtitle={t('credentials.subtitle')} />
            }
            loading={repositoriesLoading}
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
