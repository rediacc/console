import React, { useCallback, useState } from 'react';
import { Alert, Button, Flex, Space, Table, Tag, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useGetTeamMachines } from '@/api/api-hooks.generated';
import {
  useCreateRepository,
  usePromoteRepositoryToGrand,
  useGetTeamRepositories,
  useUpdateRepositoryName,
  useUpdateRepositoryTag,
} from '@/api/api-hooks.generated';
import { useGetTeamStorages } from '@/api/api-hooks.generated';
import { useGetOrganizationTeams } from '@/api/api-hooks.generated';
import { createActionColumn } from '@/components/common/columns/factories/action';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import ResourceListView from '@/components/common/ResourceListView';
import { useConfirmDialog } from '@/hooks/useConfirmDialog';
import { useDialogState } from '@/hooks/useDialogState';
import { useQueueAction } from '@/hooks/useQueueAction';
import { getGrandVaultForOperation } from '@/platform';
import { useAppSelector } from '@/store/store';
import { showMessage } from '@/utils/messages';
import { DesktopOutlined } from '@/utils/optimizedIcons';
import { DEFAULTS } from '@rediacc/shared/config';
import { useRepositoryColumns, useSystemContainerColumns } from './columns';
import { FunctionModalWrapper } from './components/FunctionModalWrapper';
import { RepositoryActionsMenu } from './components/RepositoryActionsMenu';
import { RepositoryMobileCard } from './components/RepositoryMobileCard';
import { SSHKeyWarning } from './components/SSHKeyWarning';
import {
  handleForkFunction,
  handlePushFunction,
  handlePullFunction,
  handleCustomFunction,
  isPushFunctionData,
  isForkFunctionData,
  isPullFunctionData,
} from './handlers';
import { useConfirmForkDeletion } from './hooks/useConfirmForkDeletion';
import { useConfirmRepositoryDeletion } from './hooks/useConfirmRepositoryDeletion';
import { useQuickRepositoryAction } from './hooks/useQuickRepositoryAction';
import { useRepositoryActions } from './hooks/useRepositoryActions';
import { useRepositoryTableState } from './hooks/useRepositoryTableState';
import type { FunctionExecutionContext, FunctionData } from './hooks/useFunctionExecution';
import type {
  Container,
  MachineRepositoryTableProps,
  Repository,
  RepositoryTableRow,
} from './types';
import type { ColumnsType } from 'antd/es/table';

export const MachineRepositoryTable: React.FC<MachineRepositoryTableProps> = ({
  machine,
  onActionComplete,
  hideSystemInfo = false,
  onCreateRepository,
  onRepositoryClick,
  highlightedRepository: _highlightedRepository,
  onContainerClick: _onContainerClick,
  highlightedContainer: _highlightedContainer,
  isLoading,
  onRefreshMachines: _onRefreshMachines,
  refreshKey,
  onQueueItemCreated,
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions']);
  const navigate = useNavigate();
  const { confirm, modal, contextHolder } = useConfirmDialog();
  const userEmail = useAppSelector((state) => state.auth.user?.email ?? '');
  // Placeholder for future system containers feature
  const [systemContainers, setSystemContainers] = useState<Container[]>([]);
  void systemContainers;
  void setSystemContainers;
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null);
  const functionModal = useDialogState<void>();
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null);

  const { executeTyped, executeDynamic, isExecuting } = useQueueAction();
  const { data: teams } = useGetOrganizationTeams();
  const {
    data: teamRepositories = [],
    isLoading: repositoriesLoading,
    refetch: refetchRepos,
  } = useGetTeamRepositories(machine.teamName ?? undefined);
  const { data: teamMachines = [] } = useGetTeamMachines(machine.teamName ?? undefined);
  const { data: teamStorages = [] } = useGetTeamStorages(machine.teamName ?? undefined);
  const createRepositoryMutation = useCreateRepository();
  const promoteRepoMutation = usePromoteRepositoryToGrand();
  const updateRepoNameMutation = useUpdateRepositoryName();
  const updateRepoTagMutation = useUpdateRepositoryTag();

  const { loading, error, containersData, groupedRepositories } = useRepositoryTableState({
    machine,
    teamRepositories,
    repositoriesLoading,
    refreshKey,
  });

  const { repositoryStatusColumn, repositoryNameColumn } = useRepositoryColumns(teamRepositories);
  const { systemContainerColumns } = useSystemContainerColumns();

  const { executeQuickAction } = useQuickRepositoryAction({
    teamRepositories: teamRepositories as Parameters<
      typeof useQuickRepositoryAction
    >[0]['teamRepositories'],
    machine: machine as Parameters<typeof useQuickRepositoryAction>[0]['machine'],
    executeDynamic: executeDynamic as Parameters<
      typeof useQuickRepositoryAction
    >[0]['executeDynamic'],
    onQueueItemCreated,
    t,
  });

  const { confirmForkDeletion } = useConfirmForkDeletion({
    teamRepositories: teamRepositories as Parameters<
      typeof useConfirmForkDeletion
    >[0]['teamRepositories'],
    machine: machine as Parameters<typeof useConfirmForkDeletion>[0]['machine'],
    confirm: confirm as Parameters<typeof useConfirmForkDeletion>[0]['confirm'],
    executeTyped: executeTyped as Parameters<typeof useConfirmForkDeletion>[0]['executeTyped'],
    onQueueItemCreated,
    t,
  });

  const { confirmDeletion: confirmRepositoryDeletion } = useConfirmRepositoryDeletion({
    teamRepositories: teamRepositories as Parameters<
      typeof useConfirmRepositoryDeletion
    >[0]['teamRepositories'],
    modal,
    t,
    onConfirm: async (context) => {
      const grandRepoVault =
        getGrandVaultForOperation(
          context.repositoryGuid!,
          context.repositoryGuid,
          teamRepositories
        ) ?? '{}';

      const repoData = teamRepositories.find((r) => r.repositoryGuid === context.repositoryGuid);

      const result = await executeTyped('repository_delete', {
        params: {
          grand: context.repositoryGuid ?? undefined,
        },
        teamName: machine.teamName ?? '',
        machineName: machine.machineName ?? '',
        bridgeName: machine.bridgeName ?? '',
        priority: 4,
        addedVia: 'machine-Repository-list-delete-grand',
        machineVault: machine.vaultContent ?? '{}',
        repositoryGuid: context.repositoryGuid ?? undefined,
        vaultContent: grandRepoVault,
        repositoryNetworkId: context.repositoryNetworkId ?? undefined,
      });

      if (result.success) {
        if (result.taskId) {
          showMessage(
            'success',
            t('resources:repositories.deleteGrandQueued', {
              name: repoData?.repositoryName ?? DEFAULTS.RESOURCE.TYPE,
            })
          );
          if (onQueueItemCreated) {
            onQueueItemCreated(result.taskId, machine.machineName ?? '');
          }
          showMessage('success', t('resources:repositories.deleteGrandSuccess'));
        } else if (result.isQueued) {
          showMessage('info', t('resources:repositories.highestPriorityQueued'));
        }
      } else {
        showMessage('error', result.error ?? t('resources:repositories.deleteGrandFailed'));
        throw new Error(result.error ?? t('resources:repositories.deleteGrandFailed'));
      }
    },
  });

  const { handlePromoteToGrand, handleRenameRepo, handleRenameTag } = useRepositoryActions({
    teamName: machine.teamName ?? '',
    teamRepositories,
    confirm,
    modal,
    promoteRepoMutation,
    updateRepoNameMutation,
    updateRepoTagMutation,
    onActionComplete,
    t,
  });

  const handleRefresh = () => {
    if (onActionComplete) {
      onActionComplete();
    }
  };

  const handleRunFunction = useCallback(
    (repository: Repository, functionName?: string) => {
      setSelectedRepository(repository);
      setSelectedFunction(functionName ?? null);
      functionModal.open();
    },
    [functionModal]
  );

  const closeModalAndReset = () => {
    functionModal.close();
    setSelectedRepository(null);
  };

  const createRepositoryCredential = async (repositoryName: string, tag: string) => {
    await createRepositoryMutation.mutateAsync({
      teamName: machine.teamName ?? '',
      repositoryName,
      repositoryTag: tag,
      parentRepositoryName: repositoryName,
      vaultContent: '{}',
    });
    const { data: updatedRepos } = await refetchRepos();
    const newRepo = updatedRepos?.find(
      (r) => r.repositoryName === repositoryName && r.repositoryTag === tag
    );
    if (!newRepo?.repositoryGuid) throw new Error('Could not find newly created Repository');
    return newRepo;
  };

  const handleFunctionSubmit = async (functionData: FunctionData) => {
    if (!selectedRepository) return;

    try {
      const context: FunctionExecutionContext = {
        selectedRepository,
        teamRepositories: teamRepositories as FunctionExecutionContext['teamRepositories'],
        machine: machine as FunctionExecutionContext['machine'],
        teamMachines: teamMachines as FunctionExecutionContext['teamMachines'],
        teamStorages: teamStorages as FunctionExecutionContext['teamStorages'],
        executeTyped: executeTyped as FunctionExecutionContext['executeTyped'],
        executeDynamic: executeDynamic as FunctionExecutionContext['executeDynamic'],
        createRepositoryCredential:
          createRepositoryCredential as FunctionExecutionContext['createRepositoryCredential'],
        onQueueItemCreated,
        closeModal: closeModalAndReset,
        t,
      };

      // Use type guards for proper type narrowing
      const functionDataWithParams = { ...functionData, params: functionData.params };

      if (isForkFunctionData(functionDataWithParams)) {
        await handleForkFunction(functionDataWithParams, context);
        return;
      }

      if (isPushFunctionData(functionDataWithParams)) {
        await handlePushFunction(functionDataWithParams, context);
        return;
      }

      if (isPullFunctionData(functionDataWithParams)) {
        await handlePullFunction(functionDataWithParams, context);
        return;
      }

      // For all other functions, use the custom handler
      await handleCustomFunction({ ...functionData, params: functionData.params }, context);
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : t('resources:repositories.failedToCreateQueueItem');
      showMessage('error', errorMessage);
    }
  };

  const getTableDataSource = (): RepositoryTableRow[] => {
    const tableData: RepositoryTableRow[] = [];

    groupedRepositories.forEach((group) => {
      if (group.grandTag) {
        tableData.push({
          ...group.grandTag,
          key: `repo-${group.name}-${group.grandTag.repositoryTag ?? DEFAULTS.REPOSITORY.TAG}`,
        });
      }

      group.forkTags.forEach((fork) => {
        tableData.push({
          ...fork,
          key: `repo-${fork.name}-${fork.repositoryTag ?? DEFAULTS.REPOSITORY.TAG}`,
        });
      });
    });

    return tableData;
  };

  const columns: ColumnsType<RepositoryTableRow> = [
    repositoryStatusColumn,
    repositoryNameColumn,
    createActionColumn<RepositoryTableRow>({
      title: t('common:table.actions'),
      fixed: 'right',
      renderActions: (record) => (
        <RepositoryActionsMenu
          record={record}
          teamRepositories={teamRepositories}
          machine={machine}
          userEmail={userEmail}
          containersData={containersData}
          isExecuting={isExecuting}
          onQuickAction={executeQuickAction}
          onRunFunction={handleRunFunction}
          onPromoteToGrand={handlePromoteToGrand}
          onDeleteFork={confirmForkDeletion}
          onRenameTag={handleRenameTag}
          onRenameRepository={handleRenameRepo}
          onDeleteGrandRepository={confirmRepositoryDeletion}
          onRepositoryClick={onRepositoryClick}
          onViewContainers={(repo) =>
            navigate(
              `/machines/${machine.machineName ?? ''}/repositories/${repo.name}/containers`,
              {
                state: { machine, Repository: repo },
              }
            )
          }
          onCreateRepository={onCreateRepository}
          t={t}
        />
      ),
    }),
  ];

  const mobileRender = useCallback(
    (record: RepositoryTableRow) => (
      <RepositoryMobileCard
        record={record}
        teamRepositories={teamRepositories}
        machineName={machine.machineName ?? ''}
        onNavigateToContainers={(repo) =>
          navigate(`/machines/${machine.machineName ?? ''}/repositories/${repo.name}/containers`, {
            state: { machine, Repository: repo },
          })
        }
        onRepositoryClick={onRepositoryClick}
        onQuickAction={executeQuickAction}
        onRunFunction={handleRunFunction}
        onConfirmForkDeletion={confirmForkDeletion}
        onConfirmRepositoryDeletion={confirmRepositoryDeletion}
        t={t}
      />
    ),
    [
      t,
      machine,
      navigate,
      executeQuickAction,
      handleRunFunction,
      confirmForkDeletion,
      confirmRepositoryDeletion,
      teamRepositories,
      onRepositoryClick,
    ]
  );

  if (loading) {
    return (
      <Flex data-testid="machine-repo-list-loading">
        <LoadingWrapper
          loading
          centered
          minHeight={200}
          tip={t('resources:repositories.fetchingRepos')}
        >
          <Flex />
        </LoadingWrapper>
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex data-testid="machine-repo-list-error">
        <Alert
          message={t('common:messages.error')}
          description={error}
          type="error"
          action={
            <Tooltip title={t('common:actions.retry')}>
              <Button
                onClick={handleRefresh}
                data-testid="machine-repo-list-retry"
                aria-label={t('common:actions.retry')}
              />
            </Tooltip>
          }
        />
      </Flex>
    );
  }

  return (
    <Flex vertical className="overflow-auto relative w-full" data-testid="machine-repo-list">
      {isLoading && (
        <Flex
          align="center"
          justify="center"
          className="absolute"
          // eslint-disable-next-line no-restricted-syntax
          style={{ inset: 0, zIndex: 1000 }}
        >
          <LoadingWrapper loading centered minHeight={120} tip={t('common:general.refreshing')}>
            <Flex />
          </LoadingWrapper>
        </Flex>
      )}

      {hideSystemInfo && (
        <Flex data-testid="machine-repo-list-machine-header">
          <Space direction="vertical" size="small">
            <Space>
              {/* eslint-disable-next-line no-restricted-syntax */}
              <Typography.Text style={{ fontSize: 16 }}>
                <DesktopOutlined />
              </Typography.Text>
              <Typography.Title level={4} data-testid="machine-repo-list-machine-name">
                {machine.machineName}
              </Typography.Title>
            </Space>
            <Space wrap size={8}>
              <Tag data-testid="machine-repo-list-team-tag">{machine.teamName ?? ''}</Tag>
              <Tag data-testid="machine-repo-list-bridge-tag">{machine.bridgeName ?? ''}</Tag>
              {machine.regionName && (
                <Tag data-testid="machine-repo-list-region-tag">{machine.regionName}</Tag>
              )}
              <Tag data-testid="machine-repo-list-queue-tag">
                {machine.queueCount} {t('machines:queueItems')}
              </Tag>
            </Space>
          </Space>
        </Flex>
      )}

      <SSHKeyWarning
        teamName={machine.teamName ?? ''}
        teams={teams as Parameters<typeof SSHKeyWarning>[0]['teams']}
        t={t}
      />

      <Flex className="w-full">
        <ResourceListView<RepositoryTableRow>
          loading={loading}
          data={getTableDataSource()}
          columns={columns}
          rowKey={(record) =>
            record.key ?? `${record.name}-${record.repositoryTag ?? DEFAULTS.REPOSITORY.TAG}`
          }
          pagination={false}
          emptyDescription={t('resources:repositories.noRepositories')}
          mobileRender={mobileRender}
          data-testid="machine-repo-list-table"
        />
      </Flex>

      {systemContainers.length > 0 && !hideSystemInfo && (
        <Flex vertical data-testid="machine-repo-list-system-containers">
          <Typography.Title level={5} data-testid="machine-repo-list-system-containers-title">
            {t('resources:repositories.systemContainers')}
          </Typography.Title>
          <Table<Container>
            columns={systemContainerColumns}
            dataSource={systemContainers}
            rowKey="id"
            pagination={false}
            scroll={{ x: 'max-content' }}
            data-testid="machine-repo-list-system-containers-table"
          />
        </Flex>
      )}

      <FunctionModalWrapper
        isOpen={functionModal.isOpen}
        onCancel={() => {
          functionModal.close();
          setSelectedRepository(null);
          setSelectedFunction(null);
        }}
        onSubmit={handleFunctionSubmit}
        selectedRepository={selectedRepository}
        selectedFunction={selectedFunction}
        machine={machine}
        teamRepositories={teamRepositories}
        isExecuting={isExecuting}
        t={t}
      />

      {contextHolder}
    </Flex>
  );
};
