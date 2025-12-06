import React, { useCallback, useEffect, useMemo } from 'react';
import { Alert, Button, Modal, Space, Tag, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import styled, { useTheme } from 'styled-components';
import {
  PlusOutlined,
  ReloadOutlined,
  EditOutlined,
  DeleteOutlined,
  HistoryOutlined,
  InboxOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';

const { Text } = Typography;

const InlineList = styled.ul`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  margin-bottom: 0;
  padding-left: 20px;
`;
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import TeamSelector from '@/components/common/TeamSelector';
import { ActionButtonGroup, ActionButtonConfig } from '@/components/common/ActionButtonGroup';
import { createActionColumn } from '@/components/common/columns';
import ResourceListView, {
  COLUMN_WIDTHS,
  COLUMN_RESPONSIVE,
} from '@/components/common/ResourceListView';
import {
  useRepos,
  useCreateRepo,
  useUpdateRepoName,
  useDeleteRepo,
  useUpdateRepoVault,
  Repo,
} from '@/api/queries/repos';
import { useMachines } from '@/api/queries/machines';
import { useStorage } from '@/api/queries/storage';
import { useDropdownData } from '@/api/queries/useDropdownData';
import { useRepoCreation } from '@/hooks/useRepoCreation';
import { useQueueAction } from '@/hooks/useQueueAction';
import {
  useUnifiedModal,
  useTeamSelection,
  usePagination,
  useTraceModal,
  useQueueTraceModal,
  useAsyncAction,
} from '@/hooks';
import { showMessage } from '@/utils/messages';
import { QueueFunction } from '@/api/queries/queue';
import type { QueueActionParams } from '@/services/queueActionService';
import {
  PageWrapper,
  SectionStack,
  SectionHeading,
  ListTitleRow,
  ListTitle,
  ListSubtitle,
} from '@/components/ui';
import { featureFlags } from '@/config/featureFlags';
import { getAffectedResources as coreGetAffectedResources } from '@/core';

interface CredentialsLocationState {
  createRepo?: boolean;
  selectedTeam?: string;
  selectedMachine?: string;
  selectedTemplate?: string;
}

type RepoFormValues = {
  repoName?: string;
  vaultContent?: string;
  teamName?: string;
  [key: string]: unknown;
};

type RepoModalData = Partial<Repo> & Record<string, unknown>;

const CredentialsPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common']);
  const theme = useTheme();
  const [modal, contextHolder] = Modal.useModal();
  const location = useLocation();
  const navigate = useNavigate();

  // Use custom hooks for common patterns
  const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection();
  const {
    modalState: unifiedModalState,
    currentResource,
    openModal: openUnifiedModal,
    closeModal: closeUnifiedModal,
  } = useUnifiedModal<Repo & Record<string, unknown>>('repo');
  const {
    page: repoPage,
    pageSize: repoPageSize,
    setPage: setRepoPage,
    setPageSize: setRepoPageSize,
  } = usePagination({ defaultPageSize: 15 });

  // Modal state management with new hooks
  const queueTrace = useQueueTraceModal();
  const auditTrace = useTraceModal();

  // Async action handler
  const { execute } = useAsyncAction();

  const { data: dropdownData } = useDropdownData();

  const {
    data: repos = [],
    isLoading: reposLoading,
    refetch: refetchRepos,
  } = useRepos(selectedTeams.length > 0 ? selectedTeams : undefined);

  const { data: machines = [] } = useMachines(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    selectedTeams.length > 0
  );

  const { data: storages = [] } = useStorage(selectedTeams.length > 0 ? selectedTeams : undefined);

  const createRepoMutation = useCreateRepo();
  const updateRepoNameMutation = useUpdateRepoName();
  const deleteRepoMutation = useDeleteRepo();
  const updateRepoVaultMutation = useUpdateRepoVault();

  const { createRepo: createRepoWithQueue, isCreating } = useRepoCreation(machines);
  const { executeAction, isExecuting } = useQueueAction();

  const originalRepos = useMemo(
    () => repos.filter((repo) => !repo.grandGuid || repo.grandGuid === repo.repoGuid),
    [repos]
  );

  // Helper function to find affected resources when deleting a repo
  // Uses core repo relationship service
  const getAffectedResources = useCallback(
    (repo: Repo) => {
      return coreGetAffectedResources(repo, repos, machines);
    },
    [repos, machines]
  );

  const handleDeleteRepo = useCallback(
    (repo: Repo) => {
      const { isCredential, forks, affectedMachines } = getAffectedResources(repo);

      // For credential deletion with machine deployments - BLOCK
      if (isCredential && affectedMachines.length > 0) {
        modal.error({
          title: t('repos.cannotDeleteCredential'),
          content: (
            <div>
              <Text>
                {forks.length > 0
                  ? t('repos.credentialHasDeploymentsWithForks', {
                      count: affectedMachines.length,
                      forkCount: forks.length,
                    })
                  : t('repos.credentialHasDeployments', {
                      count: affectedMachines.length,
                    })}
              </Text>

              {forks.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <Text weight="bold">{t('repos.affectedForks')}</Text>
                  <InlineList>
                    {forks.map((fork) => (
                      <li key={fork.repoGuid}>
                        {fork.repoName}
                        {fork.repoTag ? `:${fork.repoTag}` : ''}
                      </li>
                    ))}
                  </InlineList>
                </div>
              )}

              <div style={{ marginTop: 16 }}>
                <Text weight="bold">{t('repos.affectedMachines')}</Text>
                <InlineList>
                  {affectedMachines.map((machine) => (
                    <li key={machine.machineName}>
                      <Text weight="bold">{machine.machineName}</Text>
                      <Text type="secondary"> ({machine.repoNames.join(', ')})</Text>
                    </li>
                  ))}
                </InlineList>
              </div>

              <Alert
                variant="warning"
                message={t('repos.removeDeploymentsFirst')}
                showIcon
                icon={<WarningOutlined />}
                style={{ marginTop: 16 }}
              />
            </div>
          ),
          okText: t('common:actions.close'),
        });
        return;
      }

      // For fork deletion with machine deployments - WARNING but allow
      if (!isCredential && affectedMachines.length > 0) {
        modal.confirm({
          title: t('repos.deleteRepo'),
          content: (
            <div>
              <Text>{t('repos.confirmDelete', { repoName: repo.repoName })}</Text>

              <Alert
                variant="warning"
                message={t('repos.machinesWillLoseAccess')}
                description={
                  <InlineList>
                    {affectedMachines.map((machine) => (
                      <li key={machine.machineName}>
                        <Text weight="bold">{machine.machineName}</Text>
                      </li>
                    ))}
                  </InlineList>
                }
                showIcon
                icon={<WarningOutlined />}
                style={{ marginTop: 16 }}
              />
            </div>
          ),
          okText: t('common:actions.delete'),
          okType: 'danger',
          cancelText: t('common:actions.cancel'),
          onOk: async () => {
            try {
              await deleteRepoMutation.mutateAsync({
                teamName: repo.teamName,
                repoName: repo.repoName,
              });
              showMessage('success', t('repos.deleteSuccess'));
              refetchRepos();
            } catch {
              showMessage('error', t('repos.deleteError'));
            }
          },
        });
        return;
      }

      // For credential deletion without deployments or fork deletion without deployments - simple confirm
      modal.confirm({
        title: isCredential ? t('repos.deleteCredential') : t('repos.deleteRepo'),
        content: isCredential
          ? t('repos.confirmDeleteCredential', { repoName: repo.repoName })
          : t('repos.confirmDelete', { repoName: repo.repoName }),
        okText: t('common:actions.delete'),
        okType: 'danger',
        cancelText: t('common:actions.cancel'),
        onOk: async () => {
          try {
            await deleteRepoMutation.mutateAsync({
              teamName: repo.teamName,
              repoName: repo.repoName,
            });
            showMessage('success', t('repos.deleteSuccess'));
            refetchRepos();
          } catch {
            showMessage('error', t('repos.deleteError'));
          }
        },
      });
    },
    [deleteRepoMutation, getAffectedResources, modal, refetchRepos, t]
  );

  const handleUnifiedModalSubmit = useCallback(
    async (data: RepoFormValues) => {
      await execute(
        async () => {
          if (unifiedModalState.mode === 'create') {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const result = await createRepoWithQueue(data as any);

            if (result.success) {
              closeUnifiedModal();

              if (result.taskId) {
                queueTrace.open(result.taskId, result.machineName);
              } else {
                refetchRepos();
              }
            } else {
              showMessage('error', result.error || t('repos.failedToCreateRepo'));
            }
          } else if (currentResource) {
            const currentName = currentResource.repoName;
            const newName = data.repoName;

            if (newName && newName !== currentName) {
              await updateRepoNameMutation.mutateAsync({
                teamName: currentResource.teamName,
                currentRepoName: currentName,
                newRepoName: newName,
              });
            }

            const vaultData = data.vaultContent;
            if (vaultData && vaultData !== currentResource.vaultContent) {
              await updateRepoVaultMutation.mutateAsync({
                teamName: currentResource.teamName,
                repoName: newName || currentName,
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
      createRepoWithQueue,
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
            repoName: currentResource.repoName,
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
          addedVia: 'repo-table',
          teamVault:
            teams.find((team) => team.teamName === currentResource.teamName)?.vaultContent || '{}',
          repoGuid: currentResource.repoGuid,
          vaultContent: currentResource.vaultContent || '{}',
          repoNetworkId: currentResource.repoNetworkId,
          repoNetworkMode: currentResource.repoNetworkMode,
          repoTag: currentResource.repoTag,
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
            showMessage('success', t('repos.queueItemCreated'));
            queueTrace.open(result.taskId, machineEntry.value);
          } else if (result.isQueued) {
            showMessage(
              'info',
              t('resources:messages.highestPriorityQueued', { resourceType: 'repo' })
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
    createRepoMutation.isPending || updateRepoNameMutation.isPending || isCreating || isExecuting;

  const isUpdatingVault = updateRepoVaultMutation.isPending;

  useEffect(() => {
    const state = location.state as CredentialsLocationState | null;
    if (state?.createRepo) {
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

  const repoColumns = useMemo(
    () => [
      {
        title: t('repos.repoName'),
        dataIndex: 'repoName',
        key: 'repoName',
        width: COLUMN_WIDTHS.NAME,
        ellipsis: true,
        render: (text: string) => (
          <Space>
            <InboxOutlined style={{ color: theme.colors.primary }} />
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
      createActionColumn<Repo>({
        width: COLUMN_WIDTHS.ACTIONS_WIDE,
        renderActions: (record) => {
          const buttons: ActionButtonConfig<Repo>[] = [
            {
              type: 'edit',
              icon: <EditOutlined />,
              tooltip: 'common:actions.edit',
              onClick: (r: Repo) => openUnifiedModal('edit', r as Repo & Record<string, unknown>),
              variant: 'primary',
            },
            {
              type: 'trace',
              icon: <HistoryOutlined />,
              tooltip: 'machines:trace',
              onClick: (r: Repo) =>
                auditTrace.open({
                  entityType: 'Repo',
                  entityIdentifier: r.repoName,
                  entityName: r.repoName,
                }),
              variant: 'default',
            },
            {
              type: 'delete',
              icon: <DeleteOutlined />,
              tooltip: 'common:actions.delete',
              onClick: handleDeleteRepo,
              variant: 'primary',
              danger: true,
            },
          ];

          return (
            <ActionButtonGroup<Repo>
              buttons={buttons}
              record={record}
              idField="repoGuid"
              testIdPrefix="resources-repo"
              t={t}
            />
          );
        },
      }),
    ],
    [
      auditTrace,
      handleDeleteRepo,
      openUnifiedModal,
      t,
      theme.colors.primary,
      theme.colors.secondary,
    ]
  );

  const hasTeamSelection = selectedTeams.length > 0;
  const displayedRepos = hasTeamSelection ? originalRepos : [];
  const emptyDescription = hasTeamSelection
    ? t('repos.noRepos', { defaultValue: 'No repos found in this team' })
    : t('teams.selectTeamPrompt', { defaultValue: 'Select a team to view its resources' });

  return (
    <>
      <PageWrapper>
        <SectionStack>
          <SectionHeading level={3}>
            {t('credentials.heading', { defaultValue: 'Repo Credentials' })}
          </SectionHeading>

          <div style={{ width: '100%', maxWidth: 420 }}>
            <TeamSelector
              data-testid="resources-team-selector"
              teams={teams}
              selectedTeams={selectedTeams}
              onChange={setSelectedTeams}
              loading={teamsLoading}
              placeholder={t('teams.selectTeamToView', {
                defaultValue: 'Select a team to view its resources',
              })}
              style={{ width: '100%' }}
            />
          </div>

          <ResourceListView<Repo>
            title={
              <ListTitleRow>
                <ListTitle>{t('credentials.title', { defaultValue: 'Credentials' })}</ListTitle>
                <ListSubtitle>
                  {t('credentials.subtitle', {
                    defaultValue: 'Manage repo credentials and deployments',
                  })}
                </ListSubtitle>
              </ListTitleRow>
            }
            loading={reposLoading}
            data={displayedRepos}
            columns={repoColumns}
            rowKey="repoGuid"
            data-testid="resources-repo-table"
            resourceType="repos"
            emptyDescription={emptyDescription}
            pagination={
              hasTeamSelection
                ? {
                    current: repoPage,
                    pageSize: repoPageSize,
                    total: displayedRepos.length,
                    showSizeChanger: true,
                    pageSizeOptions: ['10', '20', '50', '100'],
                    showTotal: (total: number, range: [number, number]) =>
                      `${t('common:general.showingRecords', {
                        start: range[0],
                        end: range[1],
                        total,
                      })}`,
                    onChange: (page: number, size: number) => {
                      setRepoPage(page);
                      if (size && size !== repoPageSize) {
                        setRepoPageSize(size);
                        setRepoPage(1);
                      }
                    },
                    position: ['bottomRight'],
                  }
                : false
            }
            actions={
              hasTeamSelection ? (
                <>
                  <Tooltip title={t('repos.createRepo')}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      data-testid="resources-create-repositorie-button"
                      onClick={() => openUnifiedModal('create', undefined, 'credentials-only')}
                      aria-label={t('repos.createRepo')}
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
        </SectionStack>
      </PageWrapper>

      <UnifiedResourceModal
        data-testid="resources-repo-modal"
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType="repo"
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
        functionCategories={['repo', 'backup', 'network']}
        hiddenParams={['repo', 'grand']}
        defaultParams={
          currentResource
            ? { repo: currentResource.repoGuid, grand: currentResource.grandGuid || '' }
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
