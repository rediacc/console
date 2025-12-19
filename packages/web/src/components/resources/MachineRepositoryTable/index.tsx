import React, { useState } from 'react';
import { Alert, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import {
  useCreateRepository,
  usePromoteRepositoryToGrand,
  useRepositories,
  useUpdateRepositoryName,
  useUpdateRepositoryTag,
} from '@/api/queries/repositories';
import { useStorage } from '@/api/queries/storage';
import { useTeams } from '@/api/queries/teams';
import { createActionColumn } from '@/components/common/columns';
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import {
  RediaccAlert,
  RediaccButton,
  RediaccInput,
  RediaccStack,
  RediaccTable,
  RediaccTag,
  RediaccText,
  RediaccTooltip,
} from '@/components/ui';
import { useConfirmDialog } from '@/hooks/useConfirmDialog';
import { useDialogState } from '@/hooks/useDialogState';
import { useQueueAction } from '@/hooks/useQueueAction';
import {
  isFork as coreIsFork,
  getGrandVaultForOperation,
  preparePromotion,
} from '@/platform';
import { useAppSelector } from '@/store/store';
import { showMessage } from '@/utils/messages';
import { DesktopOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { useRepositoryColumns, useSystemContainerColumns } from './columns';
import { RepositoryActionsMenu } from './components/RepositoryActionsMenu';
import {
  handleForkFunction,
  handleDeployFunction,
  handleBackupFunction,
  handlePullFunction,
  handleCustomFunction,
} from './handlers';
import { useConfirmForkDeletion } from './hooks/useConfirmForkDeletion';
import { useConfirmRepositoryDeletion } from './hooks/useConfirmRepositoryDeletion';
import { useQuickRepositoryAction } from './hooks/useQuickRepositoryAction';
import { useRepositoryTableState } from './hooks/useRepositoryTableState';
import {
  ModalContent,
  SmallText,
  TableStateContainer,
} from './styledComponents';
import * as S from './styles';
import { getAxiosErrorMessage } from './utils';
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
  highlightedRepository,
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
  const userEmail = useAppSelector((state) => state.auth.user?.email || '');
  const [systemContainers] = useState<Container[]>([]);
  const [selectedRepository, setSelectedRepo] = useState<Repository | null>(null);
  const functionModal = useDialogState<void>();
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null);

  const { executeAction, isExecuting } = useQueueAction();
  const { data: teams } = useTeams();
  const {
    data: teamRepositories = [],
    isLoading: repositoriesLoading,
    refetch: refetchRepos,
  } = useRepositories(machine.teamName);
  const { data: teamMachines = [] } = useMachines(machine.teamName);
  const { data: teamStorages = [] } = useStorage(machine.teamName);
  const createRepositoryMutation = useCreateRepository();
  const promoteRepoMutation = usePromoteRepositoryToGrand();
  const updateRepoNameMutation = useUpdateRepositoryName();
  const updateRepoTagMutation = useUpdateRepositoryTag();

  const {
    repositories: _repos,
    systemInfo: _systemInfo,
    loading,
    error,
    servicesData: _servicesData,
    containersData,
    groupedRepositories,
    setRepos: _setRepos,
    setServicesData: _setServicesData,
    setContainersData: _setContainersData,
  } = useRepositoryTableState({
    machine,
    teamRepositories,
    repositoriesLoading,
    refreshKey,
  });

  const { repositoryStatusColumn, repositoryNameColumn } = useRepositoryColumns(teamRepositories);
  const { systemContainerColumns } = useSystemContainerColumns();

  const { executeQuickAction } = useQuickRepositoryAction({
    teamRepositories: teamRepositories as any,
    machine: machine as any,
    executeAction: executeAction as any,
    onQueueItemCreated,
    t,
  });

  const { confirmForkDeletion } = useConfirmForkDeletion({
    teamRepositories: teamRepositories as any,
    machine: machine as any,
    confirm: confirm as any,
    executeAction: executeAction as any,
    onQueueItemCreated,
    t,
  });

  const { confirmDeletion: confirmRepositoryDeletion } = useConfirmRepositoryDeletion({
    teamRepositories: teamRepositories as any,
    modal,
    t,
    onConfirm: async (context) => {
      const grandRepoVault =
        getGrandVaultForOperation(
          context.repositoryGuid!,
          context.repositoryGuid,
          teamRepositories
        ) || '{}';

      const repoData = teamRepositories.find(r => r.repositoryGuid === context.repositoryGuid);

      const params: Record<string, unknown> = {
        repository: context.repositoryGuid,
        repositoryName: context.repositoryTag,
        grand: context.repositoryGuid,
      };

      const result = await executeAction({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: 'rm',
        params,
        priority: 4,
        addedVia: 'machine-Repository-list-delete-grand',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid: context.repositoryGuid,
        vaultContent: grandRepoVault,
        repositoryNetworkId: context.repositoryNetworkId,
      });

      if (result.success) {
        if (result.taskId) {
          showMessage(
            'success',
            t('resources:repositories.deleteGrandQueued', { name: repoData?.repositoryName || 'repository' })
          );
          if (onQueueItemCreated) {
            onQueueItemCreated(result.taskId, machine.machineName);
          }
          showMessage('success', t('resources:repositories.deleteGrandSuccess'));
        } else if (result.isQueued) {
          showMessage('info', t('resources:repositories.highestPriorityQueued'));
        }
      } else {
        showMessage('error', result.error || t('resources:repositories.deleteGrandFailed'));
        throw new Error(result.error || t('resources:repositories.deleteGrandFailed'));
      }
    },
  });

  const handleRefresh = () => {
    if (onActionComplete) {
      onActionComplete();
    }
  };

  const handleRunFunction = (Repository: Repository, functionName?: string) => {
    setSelectedRepo(Repository);
    setSelectedFunction(functionName || null);
    functionModal.open();
  };

  const closeModalAndReset = () => {
    functionModal.close();
    setSelectedRepo(null);
  };

  const createRepositoryCredential = async (repositoryName: string, tag: string) => {
    await createRepositoryMutation.mutateAsync({
      teamName: machine.teamName,
      repositoryName,
      repositoryTag: tag,
      parentRepositoryName: repositoryName,
    });
    const { data: updatedRepos } = await refetchRepos();
    const newRepo = updatedRepos?.find(
      (r) => r.repositoryName === repositoryName && r.repositoryTag === tag
    );
    if (!newRepo?.repositoryGuid) throw new Error('Could not find newly created Repository');
    return newRepo;
  };


  const handlePromoteToGrand = async (Repository: Repository) => {
    const context = preparePromotion(Repository.name, Repository.repositoryTag, teamRepositories);

    if (context.status === 'error') {
      const errorKey =
        context.errorCode === 'NOT_FOUND'
          ? 'resources:repositories.RepoNotFound'
          : 'resources:repositories.alreadyOriginalRepo';
      showMessage('error', t(errorKey));
      return;
    }

    const { siblingClones, currentGrandName } = context;

    confirm({
      title: t('resources:repositories.promoteToGrandTitle'),
      content: (
        <ModalContent>
          <Typography.Paragraph>
            {t('resources:repositories.promoteToGrandMessage', {
              name: Repository.name,
              grand: currentGrandName,
            })}
          </Typography.Paragraph>
          {siblingClones.length > 0 && (
            <>
              <Typography.Paragraph>
                {t('resources:repositories.promoteWillUpdateSiblings', {
                  count: siblingClones.length,
                })}
              </Typography.Paragraph>
              <ul>
                {siblingClones.map((clone) => (
                  <li key={clone.repositoryGuid}>{clone.repositoryName}</li>
                ))}
              </ul>
            </>
          )}
          <Alert message={t('resources:repositories.promoteWarning')} type="warning" showIcon />
        </ModalContent>
      ),
      okText: t('resources:repositories.promoteButton'),
      okType: 'primary',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          await promoteRepoMutation.mutateAsync({
            teamName: machine.teamName,
            repositoryName: Repository.name,
          });
          showMessage(
            'success',
            t('resources:repositories.promoteSuccess', { name: Repository.name })
          );
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(
            error,
            t('resources:repositories.promoteFailed')
          );
          showMessage('error', errorMessage);
        }
      },
    });
  };

  const handleRenameRepo = async (Repository: Repository) => {
    let newName = Repository.name;

    modal.confirm({
      title: t('resources:repositories.renameTitle'),
      content: (
        <div>
          <Typography.Paragraph>
            {t('resources:repositories.renameMessage', { name: Repository.name })}
          </Typography.Paragraph>
          <RediaccInput
            defaultValue={Repository.name}
            placeholder={t('resources:repositories.newRepoName')}
            onChange={(e) => {
              newName = e.target.value;
            }}
            onPressEnter={(e) => {
              e.preventDefault();
            }}
            autoFocus
          />
        </div>
      ),
      okText: t('common:save'),
      cancelText: t('common:cancel'),
      onOk: async () => {
        const trimmedName = newName.trim();

        if (!trimmedName) {
          showMessage('error', t('resources:repositories.emptyNameError'));
          throw new Error(t('resources:repositories.emptyNameError'));
        }

        if (trimmedName === Repository.name) {
          showMessage('info', t('resources:repositories.nameUnchanged'));
          throw new Error(t('resources:repositories.nameUnchanged'));
        }

        const existingRepo = teamRepositories.find((r) => r.repositoryName === trimmedName);
        if (existingRepo) {
          showMessage(
            'error',
            t('resources:repositories.nameAlreadyExists', { name: trimmedName })
          );
          throw new Error(t('resources:repositories.nameAlreadyExists', { name: trimmedName }));
        }

        try {
          await updateRepoNameMutation.mutateAsync({
            teamName: machine.teamName,
            currentRepositoryName: Repository.name,
            newRepositoryName: trimmedName,
          });
          showMessage(
            'success',
            t('resources:repositories.renameSuccess', {
              oldName: Repository.name,
              newName: trimmedName,
            })
          );

          if (onActionComplete) {
            onActionComplete();
          }
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(
            error,
            t('resources:repositories.renameFailed')
          );
          showMessage('error', errorMessage);
          throw error;
        }
      },
    });
  };

  const handleRenameTag = async (Repository: Repository) => {
    let newTag = Repository.repositoryTag || 'latest';

    modal.confirm({
      title: t('resources:repositories.renameTagTitle'),
      content: (
        <div>
          <Typography.Paragraph>
            {t('resources:repositories.renameTagMessage', {
              name: Repository.name,
              tag: Repository.repositoryTag,
            })}
          </Typography.Paragraph>
          <RediaccInput
            defaultValue={Repository.repositoryTag}
            placeholder={t('resources:repositories.newTagName')}
            onChange={(e) => {
              newTag = e.target.value;
            }}
            onPressEnter={(e) => {
              e.preventDefault();
            }}
            autoFocus
          />
        </div>
      ),
      okText: t('common:save'),
      cancelText: t('common:cancel'),
      onOk: async () => {
        const trimmedTag = newTag.trim();

        if (!trimmedTag) {
          showMessage('error', t('resources:repositories.emptyTagError'));
          throw new Error(t('resources:repositories.emptyTagError'));
        }

        if (trimmedTag === Repository.repositoryTag) {
          showMessage('info', t('resources:repositories.tagUnchanged'));
          throw new Error(t('resources:repositories.tagUnchanged'));
        }

        const existingTag = teamRepositories.find(
          (r) => r.repositoryName === Repository.name && r.repositoryTag === trimmedTag
        );
        if (existingTag) {
          showMessage('error', t('resources:repositories.tagAlreadyExists', { tag: trimmedTag }));
          throw new Error(t('resources:repositories.tagAlreadyExists', { tag: trimmedTag }));
        }

        try {
          await updateRepoTagMutation.mutateAsync({
            teamName: machine.teamName,
            repositoryName: Repository.name,
            currentTag: Repository.repositoryTag || 'latest',
            newTag: trimmedTag,
          });
          showMessage(
            'success',
            t('resources:repositories.renameTagSuccess', {
              name: Repository.name,
              oldTag: Repository.repositoryTag,
              newTag: trimmedTag,
            })
          );

          if (onActionComplete) {
            onActionComplete();
          }
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(
            error,
            t('resources:repositories.renameTagFailed')
          );
          showMessage('error', errorMessage);
          throw error;
        }
      },
    });
  };


  const handleFunctionSubmit = async (functionData: FunctionData) => {
    if (!selectedRepository) return;

    try {
      const context: FunctionExecutionContext = {
        selectedRepository,
        teamRepositories: teamRepositories as any,
        machine: machine as any,
        teamMachines: teamMachines as any,
        teamStorages: teamStorages as any,
        executeAction: executeAction as any,
        createRepositoryCredential: createRepositoryCredential as any,
        onQueueItemCreated,
        closeModal: closeModalAndReset,
        t,
      };

      const functionName = functionData.function.name;

      if (functionName === 'fork') {
        await handleForkFunction(functionData, context);
        return;
      }

      if (functionName === 'deploy' && functionData.params.machines) {
        await handleDeployFunction(functionData, context);
        return;
      }

      if (functionName === 'backup' && functionData.params.storages) {
        await handleBackupFunction(functionData, context);
        return;
      }

      if (functionName === 'pull') {
        await handlePullFunction(functionData, context);
        return;
      }

      await handleCustomFunction(functionData, context);
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
          key: `repo-${group.name}-${group.grandTag.repositoryTag || 'latest'}`,
        });
      }

      group.forkTags.forEach((fork) => {
        tableData.push({
          ...fork,
          key: `repo-${fork.name}-${fork.repositoryTag || 'latest'}`,
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
      width: DESIGN_TOKENS.DIMENSIONS.CARD_WIDTH,
      fixed: 'end',
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
          onCreateRepository={onCreateRepository}
          t={t}
        />
      ),
    }),
  ];

  if (loading) {
    return (
      <TableStateContainer data-testid="machine-repo-list-loading">
        <LoadingWrapper
          loading
          centered
          minHeight={200}
          tip={t('resources:repositories.fetchingRepos')}
        >
          <div />
        </LoadingWrapper>
      </TableStateContainer>
    );
  }

  if (error) {
    return (
      <TableStateContainer data-testid="machine-repo-list-error">
        <Alert
          message={t('common:messages.error')}
          description={error}
          type="error"
          showIcon
          action={
            <RediaccTooltip title={t('common:actions.retry')}>
              <RediaccButton
                onClick={handleRefresh}
                data-testid="machine-repo-list-retry"
                aria-label={t('common:actions.retry')}
              />
            </RediaccTooltip>
          }
        />
      </TableStateContainer>
    );
  }

  return (
    <S.Container data-testid="machine-repo-list">
      {isLoading && (
        <S.LoadingOverlay>
          <LoadingWrapper loading centered minHeight={120} tip={t('common:general.refreshing')}>
            <div />
          </LoadingWrapper>
        </S.LoadingOverlay>
      )}

      {hideSystemInfo && (
        <S.MachineHeader data-testid="machine-repo-list-machine-header">
          <Space direction="vertical" size="small">
            <Space>
              <S.MachineIcon as={DesktopOutlined} />
              <S.MachineTitle
                as={Typography.Title}
                level={4}
                data-testid="machine-repo-list-machine-name"
              >
                {machine.machineName}
              </S.MachineTitle>
            </Space>
            <Space wrap size={8}>
              <RediaccTag data-testid="machine-repo-list-team-tag">{machine.teamName}</RediaccTag>
              <RediaccTag data-testid="machine-repo-list-bridge-tag">
                {machine.bridgeName}
              </RediaccTag>
              {machine.regionName && (
                <RediaccTag data-testid="machine-repo-list-region-tag">
                  {machine.regionName}
                </RediaccTag>
              )}
              <RediaccTag data-testid="machine-repo-list-queue-tag">
                {machine.queueCount} {t('machines:queueItems')}
              </RediaccTag>
            </Space>
          </Space>
        </S.MachineHeader>
      )}

      {(() => {
        const team = teams?.find((t) => t.teamName === machine.teamName);
        if (!team?.vaultContent) return null;

        let missingSSHKeys = false;
        try {
          const teamVault = JSON.parse(team.vaultContent);
          missingSSHKeys = !teamVault.SSH_PRIVATE_KEY || !teamVault.SSH_PUBLIC_KEY;
        } catch {
          return null;
        }

        return missingSSHKeys ? (
          <RediaccAlert
            spacing="default"
            variant="warning"
            showIcon
            closable
            message={t('common:vaultEditor.missingSshKeysWarning')}
            description={t('common:vaultEditor.missingSshKeysDescription')}
          />
        ) : null;
      })()}

      <S.TableStyleWrapper>
        <RediaccTable<RepositoryTableRow>
          columns={columns}
          dataSource={getTableDataSource()}
          rowKey={(record) => record.key || `${record.name}-${record.repositoryTag || 'latest'}`}
          size="sm"
          pagination={false}
          scroll={{ x: 'max-content' }}
          data-testid="machine-repo-list-table"
          rowClassName={(record) => {
            const repositoryData = teamRepositories.find(
              (r) => r.repositoryName === record.name && r.repositoryTag === record.repositoryTag
            );
            const classes = ['Repository-row'];
            if (repositoryData && coreIsFork(repositoryData)) {
              classes.push('Repository-fork-row');
            }
            if (highlightedRepository?.name === record.name) {
              classes.push('Repository-row--highlighted');
            }
            return classes.join(' ');
          }}
          locale={{
            emptyText: t('resources:repositories.noRepositories'),
          }}
          onRow={(record) => ({
            onClick: (e: React.MouseEvent<HTMLElement>) => {
              const target = e.target as HTMLElement;
              if (target.closest('button') || target.closest('.ant-dropdown')) {
                return;
              }

              navigate(`/machines/${machine.machineName}/repositories/${record.name}/containers`, {
                state: { machine, Repository: record },
              });
            },
          })}
        />
      </S.TableStyleWrapper>

      {systemContainers.length > 0 && !hideSystemInfo && (
        <S.SystemContainersWrapper data-testid="machine-repo-list-system-containers">
          <S.SystemContainersTitle
            as={Typography.Title}
            level={5}
            data-testid="machine-repo-list-system-containers-title"
          >
            {t('resources:repositories.systemContainers')}
          </S.SystemContainersTitle>
          <RediaccTable<Container>
            columns={systemContainerColumns}
            dataSource={systemContainers}
            rowKey="id"
            size="sm"
            pagination={false}
            scroll={{ x: 'max-content' }}
            data-testid="machine-repo-list-system-containers-table"
          />
        </S.SystemContainersWrapper>
      )}

      <FunctionSelectionModal
        open={functionModal.isOpen}
        onCancel={() => {
          functionModal.close();
          setSelectedRepo(null);
          setSelectedFunction(null);
        }}
        onSubmit={handleFunctionSubmit}
        title={t('machines:runFunction')}
        data-testid="machine-repo-list-function-modal"
        subtitle={
          selectedRepository && (
            <RediaccStack direction="vertical" gap="sm" fullWidth>
              <Space>
                <RediaccText>{t('resources:repositories.Repository')}:</RediaccText>
                <RediaccTag>{selectedRepository.name}</RediaccTag>
                <RediaccText>•</RediaccText>
                <RediaccText>{t('machines:machine')}:</RediaccText>
                <RediaccTag>{machine.machineName}</RediaccTag>
              </Space>
              {selectedFunction === 'push' &&
                (() => {
                  const currentRepoData = teamRepositories.find(
                    (r) =>
                      r.repositoryName === selectedRepository.name &&
                      r.repositoryTag === selectedRepository.repositoryTag
                  );
                  if (currentRepoData?.parentGuid) {
                    const parentRepo = teamRepositories.find(
                      (r) => r.repositoryGuid === currentRepoData.parentGuid
                    );
                    if (parentRepo) {
                      return (
                        <Space>
                          <SmallText color="secondary">
                            {t('resources:repositories.parentRepo', {
                              defaultValue: 'Parent Repository',
                            })}
                            :
                          </SmallText>
                          <RediaccTag>{parentRepo.repositoryName}</RediaccTag>
                          <SmallText color="secondary">→</SmallText>
                          <SmallText color="secondary">{t('common:current')}:</SmallText>
                          <RediaccTag>{selectedRepository.name}</RediaccTag>
                        </Space>
                      );
                    }
                  }
                  return null;
                })()}
            </RediaccStack>
          )
        }
        allowedCategories={['Repository', 'backup', 'network']}
        loading={isExecuting}
        showMachineSelection={false}
        teamName={machine.teamName}
        hiddenParams={['repository', 'grand', 'state']}
        defaultParams={{
          repository: (() => {
            const repository = teamRepositories.find(
              (r) =>
                r.repositoryName === selectedRepository?.name &&
                r.repositoryTag === selectedRepository?.repositoryTag
            );
            return repository?.repositoryGuid || '';
          })(),
          grand:
            teamRepositories.find(
              (r) =>
                r.repositoryName === selectedRepository?.name &&
                r.repositoryTag === selectedRepository?.repositoryTag
            )?.grandGuid || '',
          ...((selectedFunction === 'backup' ||
            selectedFunction === 'push' ||
            selectedFunction === 'deploy' ||
            selectedFunction === 'fork') &&
          selectedRepository
            ? {
                state: selectedRepository.mounted ? 'online' : 'offline',
              }
            : {}),
        }}
        initialParams={{
          ...((selectedFunction === 'fork' || selectedFunction === 'deploy') && selectedRepository
            ? {
                tag: new Date().toISOString().slice(0, 19).replace('T', '-').replace(/:/g, '-'),
              }
            : {}),
        }}
        preselectedFunction={selectedFunction || undefined}
        currentMachineName={machine.machineName}
        additionalContext={
          selectedFunction === 'push' && selectedRepository
            ? {
                sourceRepo: selectedRepository.name,
                parentRepo: (() => {
                  const currentRepoData = teamRepositories.find(
                    (r) =>
                      r.repositoryName === selectedRepository.name &&
                      r.repositoryTag === selectedRepository.repositoryTag
                  );
                  if (currentRepoData?.parentGuid) {
                    const parentRepo = teamRepositories.find(
                      (r) => r.repositoryGuid === currentRepoData.parentGuid
                    );
                    return parentRepo?.repositoryName || null;
                  }
                  return null;
                })(),
              }
            : undefined
        }
      />

      {contextHolder}
    </S.Container>
  );
};
