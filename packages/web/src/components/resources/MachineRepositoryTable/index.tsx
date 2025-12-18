import React, { useState } from 'react';
import { Alert, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { type QueueFunction } from '@/api/queries/queue';
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
  canBackupToStorage,
  isFork as coreIsFork,
  getGrandVaultForOperation,
  prepareForkDeletion,
  prepareGrandDeletion,
  preparePromotion,
} from '@/platform';
import { useAppSelector } from '@/store/store';
import { showMessage } from '@/utils/messages';
import { DesktopOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { useRepositoryColumns, useSystemContainerColumns } from './columns';
import { RepositoryActionsMenu } from './components/RepositoryActionsMenu';
import { useRepositoryTableState } from './hooks/useRepositoryTableState';
import {
  ConfirmationInput,
  ModalContent,
  SmallText,
  TableStateContainer,
} from './styledComponents';
import * as S from './styles';
import { getAxiosErrorMessage } from './utils';
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

  const getRequiredTag = (params: Record<string, unknown>, errorMsg: string): string | null => {
    const tag = typeof params.tag === 'string' ? params.tag.trim() : '';
    if (!tag) {
      showMessage('error', errorMsg);
      closeModalAndReset();
      return null;
    }
    return tag;
  };

  const showMultiTargetSummary = (
    taskIds: string[],
    total: number,
    keys: { success: string; partial: string; allFailed: string }
  ) => {
    if (taskIds.length === total) {
      showMessage('success', t(keys.success, { count: taskIds.length }));
    } else if (taskIds.length > 0) {
      showMessage('warning', t(keys.partial, { success: taskIds.length, total }));
    } else {
      showMessage('error', t(keys.allFailed));
    }
    if (onQueueItemCreated && taskIds[0]) {
      onQueueItemCreated(taskIds[0], machine.machineName);
    }
  };

  const handleQuickAction = async (
    Repository: Repository,
    functionName: string,
    priority: number = 4,
    option?: string
  ) => {
    const RepoData = teamRepositories.find(
      (r) => r.repositoryName === Repository.name && r.repositoryTag === Repository.repositoryTag
    );

    if (!RepoData || !RepoData.vaultContent) {
      showMessage(
        'error',
        t('resources:repositories.noCredentialsFound', { name: Repository.name })
      );
      return;
    }

    const grandRepoVault =
      getGrandVaultForOperation(RepoData.repositoryGuid, RepoData.grandGuid, teamRepositories) ||
      RepoData.vaultContent;

    const params: Record<string, unknown> = {
      repository: RepoData.repositoryGuid,
      repositoryName: RepoData.repositoryName,
      grand: RepoData.grandGuid || '',
    };

    if (option) {
      params.option = option;
    }

    const result = await executeAction({
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      functionName,
      params,
      priority,
      addedVia: 'machine-Repository-list-quick',
      machineVault: machine.vaultContent || '{}',
      repositoryGuid: RepoData.repositoryGuid,
      vaultContent: grandRepoVault,
      repositoryNetworkId: RepoData.repositoryNetworkId,
      repositoryNetworkMode: RepoData.repositoryNetworkMode,
      repositoryTag: RepoData.repositoryTag,
    });

    if (result.success) {
      if (result.taskId) {
        showMessage('success', t('resources:repositories.queueItemCreated'));
        if (onQueueItemCreated) {
          onQueueItemCreated(result.taskId, machine.machineName);
        }
      } else if (result.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'));
      }
    } else {
      showMessage('error', result.error || t('resources:repositories.failedToCreateQueueItem'));
    }
  };

  const handleDeleteFork = async (Repository: Repository) => {
    const context = prepareForkDeletion(
      Repository.name,
      Repository.repositoryTag,
      teamRepositories
    );

    if (context.status === 'error') {
      const errorKey =
        context.errorCode === 'NOT_FOUND'
          ? 'resources:repositories.RepoNotFound'
          : 'resources:repositories.cannotDeleteGrandRepo';
      showMessage('error', t(errorKey));
      return;
    }

    const parentName = context.parentName || Repository.name;

    confirm({
      title: t('resources:repositories.deleteCloneConfirmTitle'),
      content: t('resources:repositories.deleteCloneConfirmMessage', {
        name: Repository.name,
        tag: Repository.repositoryTag || 'latest',
        parentName,
      }),
      okText: t('common:delete'),
      okType: 'danger',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          const grandRepoVault =
            getGrandVaultForOperation(
              context.repositoryGuid!,
              context.grandGuid,
              teamRepositories
            ) || '{}';

          const params: Record<string, unknown> = {
            repository: context.repositoryGuid,
            repositoryName: context.repositoryTag,
            grand: context.grandGuid,
          };

          const result = await executeAction({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            addedVia: 'machine-Repository-list-delete-clone',
            machineVault: machine.vaultContent || '{}',
            repositoryGuid: context.repositoryGuid,
            vaultContent: grandRepoVault,
            repositoryNetworkId: context.repositoryNetworkId,
          });

          if (result.success) {
            if (result.taskId) {
              showMessage(
                'success',
                t('resources:repositories.deleteCloneQueued', {
                  name: Repository.name,
                  tag: Repository.repositoryTag || 'latest',
                })
              );
              if (onQueueItemCreated) {
                onQueueItemCreated(result.taskId, machine.machineName);
              }
              showMessage('success', t('resources:repositories.deleteForkSuccess'));
            } else if (result.isQueued) {
              showMessage('info', t('resources:repositories.highestPriorityQueued'));
            }
          } else {
            showMessage('error', result.error || t('resources:repositories.deleteCloneFailed'));
          }
        } catch {
          showMessage('error', t('resources:repositories.deleteCloneFailed'));
        }
      },
    });
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
          return Promise.reject();
        }

        if (trimmedName === Repository.name) {
          showMessage('info', t('resources:repositories.nameUnchanged'));
          return Promise.reject();
        }

        const existingRepo = teamRepositories.find((r) => r.repositoryName === trimmedName);
        if (existingRepo) {
          showMessage(
            'error',
            t('resources:repositories.nameAlreadyExists', { name: trimmedName })
          );
          return Promise.reject();
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
          return Promise.reject();
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
          return Promise.reject();
        }

        if (trimmedTag === Repository.repositoryTag) {
          showMessage('info', t('resources:repositories.tagUnchanged'));
          return Promise.reject();
        }

        const existingTag = teamRepositories.find(
          (r) => r.repositoryName === Repository.name && r.repositoryTag === trimmedTag
        );
        if (existingTag) {
          showMessage('error', t('resources:repositories.tagAlreadyExists', { tag: trimmedTag }));
          return Promise.reject();
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
          return Promise.reject();
        }
      },
    });
  };

  const handleDeleteGrandRepo = async (Repository: Repository) => {
    const context = prepareGrandDeletion(
      Repository.name,
      Repository.repositoryTag,
      teamRepositories
    );

    if (context.status === 'error') {
      const errorKey =
        context.errorCode === 'NOT_FOUND'
          ? 'resources:repositories.RepoNotFound'
          : 'resources:repositories.notAGrandRepo';
      showMessage('error', t(errorKey));
      return;
    }

    if (context.status === 'blocked') {
      modal.error({
        title: t('resources:repositories.cannotDeleteHasClones'),
        content: (
          <div>
            <Typography.Paragraph>
              {t('resources:repositories.hasActiveClonesMessage', {
                name: Repository.name,
                count: context.childClones.length,
              })}
            </Typography.Paragraph>
            <RediaccText as="p" weight="bold">
              {t('resources:repositories.clonesList')}
            </RediaccText>
            <ul>
              {context.childClones.map((clone) => (
                <li key={clone.repositoryGuid}>{clone.repositoryName}</li>
              ))}
            </ul>
            <Typography.Paragraph>
              {t('resources:repositories.deleteOptionsMessage')}
            </Typography.Paragraph>
          </div>
        ),
        okText: t('common:close'),
      });
      return;
    }

    let confirmationInput = '';

    modal.confirm({
      title: t('resources:repositories.deleteGrandConfirmTitle'),
      content: (
        <ModalContent>
          <Alert
            message={t('resources:repositories.deleteGrandWarning')}
            description={t('resources:repositories.deleteGrandWarningDesc', {
              name: Repository.name,
            })}
            type="warning"
            showIcon
          />
          <RediaccText weight="bold">
            {t('resources:repositories.deleteGrandConfirmPrompt', { name: Repository.name })}
          </RediaccText>
          <ConfirmationInput
            type="text"
            placeholder={Repository.name}
            onChange={(e) => {
              confirmationInput = e.target.value;
            }}
          />
        </ModalContent>
      ),
      okText: t('common:delete'),
      okType: 'danger',
      cancelText: t('common:cancel'),
      onOk: async () => {
        if (confirmationInput !== Repository.name) {
          showMessage('error', t('resources:repositories.deleteGrandConfirmationMismatch'));
          return Promise.reject();
        }

        try {
          const grandRepoVault =
            getGrandVaultForOperation(
              context.repositoryGuid!,
              context.repositoryGuid,
              teamRepositories
            ) || '{}';

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
                t('resources:repositories.deleteGrandQueued', { name: Repository.name })
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
            return Promise.reject();
          }
        } catch {
          showMessage('error', t('resources:repositories.deleteGrandFailed'));
          return Promise.reject();
        }
      },
    });
  };

  const handleFunctionSubmit = async (functionData: {
    function: QueueFunction;
    params: Record<string, unknown>;
    priority: number;
    description: string;
  }) => {
    if (!selectedRepository) return;

    try {
      const RepoData = teamRepositories.find(
        (r) =>
          r.repositoryName === selectedRepository.name &&
          r.repositoryTag === selectedRepository.repositoryTag
      );

      if (!RepoData || !RepoData.vaultContent) {
        showMessage(
          'error',
          t('resources:repositories.noCredentialsFound', { name: selectedRepository.name })
        );
        functionModal.close();
        setSelectedRepo(null);
        return;
      }

      let grandRepoVault = RepoData.vaultContent;
      if (RepoData.grandGuid) {
        const grandRepo = teamRepositories.find((r) => r.repositoryGuid === RepoData.grandGuid);
        if (grandRepo && grandRepo.vaultContent) {
          grandRepoVault = grandRepo.vaultContent;
        }
      }

      const finalParams = { ...functionData.params };
      const repositoryGuid = RepoData.repositoryGuid;
      const vaultContent = grandRepoVault;

      if (functionData.function.name === 'fork') {
        const forkTag = getRequiredTag(functionData.params, 'Tag is required for fork');
        if (!forkTag) return;

        let newRepo;
        try {
          newRepo = await createRepositoryCredential(selectedRepository.name, forkTag);
        } catch {
          showMessage('error', t('resources:repositories.failedToCreateRepository'));
          closeModalAndReset();
          return;
        }

        try {
          const result = await executeAction({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'push',
            params: {
              repository: RepoData.repositoryGuid,
              repositoryName: RepoData.repositoryName,
              dest: newRepo.repositoryGuid,
              destName: newRepo.repositoryName,
              destinationType: 'machine',
              to: machine.machineName,
              state: selectedRepository.mounted ? 'online' : 'offline',
              grand: RepoData.grandGuid || RepoData.repositoryGuid || '',
            },
            priority: functionData.priority,
            addedVia: 'machine-Repository-list-fork',
            machineVault: machine.vaultContent || '{}',
            repositoryGuid: RepoData.repositoryGuid,
            vaultContent: grandRepoVault,
            repositoryNetworkId: newRepo.repositoryNetworkId,
            repositoryNetworkMode: newRepo.repositoryNetworkMode,
            repositoryTag: newRepo.repositoryTag,
          });

          closeModalAndReset();

          if (result.success) {
            if (result.taskId) {
              showMessage(
                'success',
                t('resources:repositories.forkStarted', {
                  dest: `${selectedRepository.name}:${forkTag}`,
                })
              );
              if (onQueueItemCreated) onQueueItemCreated(result.taskId, machine.machineName);
            } else if (result.isQueued) {
              showMessage('info', t('resources:repositories.highestPriorityQueued'));
            }
          } else {
            throw new Error(result.error || 'Failed to fork Repository');
          }
        } catch {
          showMessage('error', t('resources:repositories.failedToForkRepository'));
        }
        return;
      }

      if (functionData.function.name === 'deploy' && functionData.params.machines) {
        const machinesArray = Array.isArray(functionData.params.machines)
          ? functionData.params.machines
          : [functionData.params.machines];
        const deployTag = getRequiredTag(functionData.params, 'Tag is required for deploy');
        if (!deployTag) return;

        let newRepo;
        try {
          newRepo = await createRepositoryCredential(selectedRepository.name, deployTag);
        } catch {
          showMessage('error', t('resources:repositories.failedToCreateRepository'));
          closeModalAndReset();
          return;
        }

        const createdTaskIds: string[] = [];
        for (const targetMachine of machinesArray) {
          const destinationMachine = teamMachines.find((m) => m.machineName === targetMachine);
          if (!destinationMachine) {
            showMessage(
              'error',
              t('resources:repositories.destinationMachineNotFound', { machine: targetMachine })
            );
            continue;
          }
          try {
            const result = await executeAction({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              functionName: 'deploy',
              params: {
                ...functionData.params,
                machines: machinesArray.join(','),
                to: targetMachine,
                dest: newRepo.repositoryGuid,
                destName: newRepo.repositoryName,
                repository: RepoData.repositoryGuid,
                repositoryName: RepoData.repositoryName,
                grand: RepoData.grandGuid || RepoData.repositoryGuid || '',
                state: selectedRepository.mounted ? 'online' : 'offline',
              },
              priority: functionData.priority,
              addedVia: 'machine-Repository-list',
              machineVault: machine.vaultContent || '{}',
              destinationMachineVault: destinationMachine.vaultContent || '{}',
              repositoryGuid,
              vaultContent,
              repositoryNetworkId: newRepo.repositoryNetworkId,
              repositoryNetworkMode: newRepo.repositoryNetworkMode,
              repositoryTag: newRepo.repositoryTag,
            });
            if (result.success && result.taskId) createdTaskIds.push(result.taskId);
          } catch {
            showMessage(
              'error',
              t('resources:repositories.failedToDeployTo', { machine: targetMachine })
            );
          }
        }

        closeModalAndReset();
        showMultiTargetSummary(createdTaskIds, machinesArray.length, {
          success: 'resources:repositories.deploymentQueued',
          partial: 'resources:repositories.deploymentPartialSuccess',
          allFailed: 'resources:repositories.allDeploymentsFailed',
        });
        return;
      }

      if (functionData.function.name === 'backup' && functionData.params.storages) {
        if (!canBackupToStorage(RepoData).canBackup) {
          showMessage('error', t('resources:repositories.cannotBackupForkToStorage'));
          closeModalAndReset();
          return;
        }

        const storagesArray = Array.isArray(functionData.params.storages)
          ? functionData.params.storages
          : [functionData.params.storages];
        const createdTaskIds: string[] = [];

        for (const targetStorage of storagesArray) {
          const destinationStorage = teamStorages.find((s) => s.storageName === targetStorage);
          if (!destinationStorage) {
            showMessage(
              'error',
              t('resources:repositories.destinationStorageNotFound', { storage: targetStorage })
            );
            continue;
          }
          try {
            const result = await executeAction({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              functionName: 'backup',
              params: {
                ...functionData.params,
                storages: storagesArray.join(','),
                to: targetStorage,
                dest: RepoData.repositoryGuid,
                destName: RepoData.repositoryName,
                repository: RepoData.repositoryGuid,
                repositoryName: RepoData.repositoryName,
                grand: RepoData.grandGuid || RepoData.repositoryGuid || '',
                state: selectedRepository.mounted ? 'online' : 'offline',
              },
              priority: functionData.priority,
              addedVia: 'machine-Repository-list',
              machineVault: machine.vaultContent || '{}',
              destinationStorageVault: destinationStorage.vaultContent || '{}',
              repositoryGuid,
              vaultContent,
              repositoryNetworkId: RepoData.repositoryNetworkId,
              repositoryNetworkMode: RepoData.repositoryNetworkMode,
              repositoryTag: RepoData.repositoryTag,
            });
            if (result.success && result.taskId) createdTaskIds.push(result.taskId);
          } catch {
            showMessage(
              'error',
              t('resources:repositories.failedToBackupTo', { storage: targetStorage })
            );
          }
        }

        closeModalAndReset();
        showMultiTargetSummary(createdTaskIds, storagesArray.length, {
          success: 'resources:repositories.backupQueued',
          partial: 'resources:repositories.backupPartialSuccess',
          allFailed: 'resources:repositories.allBackupsFailed',
        });
        return;
      }

      if (functionData.function.name === 'pull') {
        finalParams.repository = RepoData.repositoryGuid;
        finalParams.grand = RepoData.grandGuid || RepoData.repositoryGuid || '';
      }

      const result = await executeAction({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: functionData.function.name,
        params: finalParams,
        priority: functionData.priority,
        addedVia: 'machine-Repository-list',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid,
        vaultContent,
        repositoryNetworkId: RepoData.repositoryNetworkId,
        repositoryNetworkMode: RepoData.repositoryNetworkMode,
        repositoryTag: RepoData.repositoryTag,
      });

      functionModal.close();
      setSelectedRepo(null);

      if (result.success) {
        if (result.taskId) {
          showMessage('success', t('resources:repositories.queueItemCreated'));
          if (onQueueItemCreated) {
            onQueueItemCreated(result.taskId, machine.machineName);
          }
        } else if (result.isQueued) {
          showMessage('info', t('resources:repositories.highestPriorityQueued'));
        }
      } else {
        throw new Error(result.error || t('resources:repositories.failedToCreateQueueItem'));
      }
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
          onQuickAction={handleQuickAction}
          onRunFunction={handleRunFunction}
          onPromoteToGrand={handlePromoteToGrand}
          onDeleteFork={handleDeleteFork}
          onRenameTag={handleRenameTag}
          onRenameRepository={handleRenameRepo}
          onDeleteGrandRepository={handleDeleteGrandRepo}
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
          <LoadingWrapper
            loading
            centered
            minHeight={120}
            tip={t('common:general.refreshing')}
          >
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

        try {
          const teamVault = JSON.parse(team.vaultContent);
          const missingSSHKeys = !teamVault.SSH_PRIVATE_KEY || !teamVault.SSH_PUBLIC_KEY;

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
        } catch {
          return null;
        }
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
