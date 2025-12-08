import React, { useState } from 'react';
import { Typography, Button, Tooltip, Input, Space, Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { type QueueFunction } from '@/api/queries/queue';
import {
  useRepos,
  useCreateRepo,
  usePromoteRepoToGrand,
  useUpdateRepoName,
  useUpdateRepoTag,
} from '@/api/queries/repos';
import { useStorage } from '@/api/queries/storage';
import { useTeams } from '@/api/queries/teams';
import { createActionColumn } from '@/components/common/columns';
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccAlert, RediaccStack, RediaccText } from '@/components/ui';
import { useConfirmDialog } from '@/hooks/useConfirmDialog';
import { useDialogState } from '@/hooks/useDialogState';
import { useQueueAction } from '@/hooks/useQueueAction';
import {
  canBackupToStorage,
  isFork as coreIsFork,
  prepareForkDeletion,
  prepareGrandDeletion,
  preparePromotion,
  getGrandVaultForOperation,
} from '@/platform';
import { useAppSelector } from '@/store/store';
import { showMessage } from '@/utils/messages';
import { DesktopOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import type { TableProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import * as S from './styles';
import type {
  MachineRepoTableProps,
  RepoTableRow,
  Container,
  Repo,
} from './types';
import { getAxiosErrorMessage } from './utils';
import { useRepoColumns, useSystemContainerColumns } from './columns';
import { RepoActionsMenu } from './components/RepoActionsMenu';
import { useRepoTableState } from './hooks/useRepoTableState';
import {
  ModalContent,
  ConfirmationInput,
  TableStateContainer,
  SmallText,
  InlineTag,
  MachineTag,
  InfoTag,
} from './styledComponents';

const RepoTableComponent = S.StyledTable as React.ComponentType<TableProps<RepoTableRow>>;
const SystemTableComponent = S.StyledTable as React.ComponentType<TableProps<Container>>;

export const MachineRepoTable: React.FC<MachineRepoTableProps> = ({
  machine,
  onActionComplete,
  hideSystemInfo = false,
  onCreateRepo,
  onRepoClick,
  highlightedRepo,
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
  const [selectedRepo, setSelectedRepo] = useState<Repo | null>(null);
  const functionModal = useDialogState<void>();
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null);

  const { executeAction, isExecuting } = useQueueAction();
  const { data: teams } = useTeams();
  const {
    data: teamRepos = [],
    isLoading: reposLoading,
    refetch: refetchRepos,
  } = useRepos(machine.teamName);
  const { data: teamMachines = [] } = useMachines(machine.teamName);
  const { data: teamStorages = [] } = useStorage(machine.teamName);
  const createRepoMutation = useCreateRepo();
  const promoteRepoMutation = usePromoteRepoToGrand();
  const updateRepoNameMutation = useUpdateRepoName();
  const updateRepoTagMutation = useUpdateRepoTag();

  const {
    repos: _repos,
    systemInfo: _systemInfo,
    loading,
    error,
    servicesData: _servicesData,
    containersData,
    groupedRepos,
    setRepos: _setRepos,
    setServicesData: _setServicesData,
    setContainersData: _setContainersData,
  } = useRepoTableState({
    machine,
    teamRepos,
    reposLoading,
    refreshKey,
  });

  const { repoStatusColumn, repoNameColumn } = useRepoColumns(teamRepos);
  const { systemContainerColumns } = useSystemContainerColumns();

  const handleRefresh = () => {
    if (onActionComplete) {
      onActionComplete();
    }
  };

  const handleRunFunction = (Repo: Repo, functionName?: string) => {
    setSelectedRepo(Repo);
    setSelectedFunction(functionName || null);
    functionModal.open();
  };

  const closeModalAndReset = () => {
    functionModal.close();
    setSelectedRepo(null);
  };

  const createRepoCredential = async (repoName: string, tag: string) => {
    await createRepoMutation.mutateAsync({
      teamName: machine.teamName,
      repoName,
      repoTag: tag,
      parentRepoName: repoName,
    });
    const { data: updatedRepos } = await refetchRepos();
    const newRepo = updatedRepos?.find((r) => r.repoName === repoName && r.repoTag === tag);
    if (!newRepo?.repoGuid) throw new Error('Could not find newly created Repo');
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
    Repo: Repo,
    functionName: string,
    priority: number = 4,
    option?: string
  ) => {
    const RepoData = teamRepos.find((r) => r.repoName === Repo.name && r.repoTag === Repo.repoTag);

    if (!RepoData || !RepoData.vaultContent) {
      showMessage('error', t('resources:repos.noCredentialsFound', { name: Repo.name }));
      return;
    }

    const grandRepoVault =
      getGrandVaultForOperation(RepoData.repoGuid, RepoData.grandGuid, teamRepos) ||
      RepoData.vaultContent;

    const params: Record<string, unknown> = {
      repo: RepoData.repoGuid,
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
      addedVia: 'machine-Repo-list-quick',
      machineVault: machine.vaultContent || '{}',
      repoGuid: RepoData.repoGuid,
      vaultContent: grandRepoVault,
      repoNetworkId: RepoData.repoNetworkId,
      repoNetworkMode: RepoData.repoNetworkMode,
      repoTag: RepoData.repoTag,
    });

    if (result.success) {
      if (result.taskId) {
        showMessage('success', t('resources:repos.queueItemCreated'));
        if (onQueueItemCreated) {
          onQueueItemCreated(result.taskId, machine.machineName);
        }
      } else if (result.isQueued) {
        showMessage('info', t('resources:repos.highestPriorityQueued'));
      }
    } else {
      showMessage('error', result.error || t('resources:repos.failedToCreateQueueItem'));
    }
  };

  const handleDeleteFork = async (Repo: Repo) => {
    const context = prepareForkDeletion(Repo.name, Repo.repoTag, teamRepos);

    if (context.status === 'error') {
      const errorKey =
        context.errorCode === 'NOT_FOUND'
          ? 'resources:repos.RepoNotFound'
          : 'resources:repos.cannotDeleteGrandRepo';
      showMessage('error', t(errorKey));
      return;
    }

    const parentName = context.parentName || Repo.name;

    confirm({
      title: t('resources:repos.deleteCloneConfirmTitle'),
      content: t('resources:repos.deleteCloneConfirmMessage', {
        name: Repo.name,
        tag: Repo.repoTag || 'latest',
        parentName,
      }),
      okText: t('common:delete'),
      okType: 'danger',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          const grandRepoVault =
            getGrandVaultForOperation(context.repoGuid!, context.grandGuid, teamRepos) || '{}';

          const params: Record<string, unknown> = {
            repo: context.repoGuid,
            grand: context.grandGuid,
          };

          const result = await executeAction({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            addedVia: 'machine-Repo-list-delete-clone',
            machineVault: machine.vaultContent || '{}',
            repoGuid: context.repoGuid,
            vaultContent: grandRepoVault,
            repoNetworkId: context.repoNetworkId,
          });

          if (result.success) {
            if (result.taskId) {
              showMessage(
                'success',
                t('resources:repos.deleteCloneQueued', {
                  name: Repo.name,
                  tag: Repo.repoTag || 'latest',
                })
              );
              if (onQueueItemCreated) {
                onQueueItemCreated(result.taskId, machine.machineName);
              }
              showMessage('success', t('resources:repos.deleteForkSuccess'));
            } else if (result.isQueued) {
              showMessage('info', t('resources:repos.highestPriorityQueued'));
            }
          } else {
            showMessage('error', result.error || t('resources:repos.deleteCloneFailed'));
          }
        } catch {
          showMessage('error', t('resources:repos.deleteCloneFailed'));
        }
      },
    });
  };

  const handlePromoteToGrand = async (Repo: Repo) => {
    const context = preparePromotion(Repo.name, Repo.repoTag, teamRepos);

    if (context.status === 'error') {
      const errorKey =
        context.errorCode === 'NOT_FOUND'
          ? 'resources:repos.RepoNotFound'
          : 'resources:repos.alreadyOriginalRepo';
      showMessage('error', t(errorKey));
      return;
    }

    const { siblingClones, currentGrandName } = context;

    confirm({
      title: t('resources:repos.promoteToGrandTitle'),
      content: (
        <ModalContent>
          <Typography.Paragraph>
            {t('resources:repos.promoteToGrandMessage', {
              name: Repo.name,
              grand: currentGrandName,
            })}
          </Typography.Paragraph>
          {siblingClones.length > 0 && (
            <>
              <Typography.Paragraph>
                {t('resources:repos.promoteWillUpdateSiblings', { count: siblingClones.length })}
              </Typography.Paragraph>
              <ul>
                {siblingClones.map((clone) => (
                  <li key={clone.repoGuid}>{clone.repoName}</li>
                ))}
              </ul>
            </>
          )}
          <Alert message={t('resources:repos.promoteWarning')} type="warning" showIcon />
        </ModalContent>
      ),
      okText: t('resources:repos.promoteButton'),
      okType: 'primary',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          await promoteRepoMutation.mutateAsync({
            teamName: machine.teamName,
            repoName: Repo.name,
          });
          showMessage('success', t('resources:repos.promoteSuccess', { name: Repo.name }));
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(error, t('resources:repos.promoteFailed'));
          showMessage('error', errorMessage);
        }
      },
    });
  };

  const handleRenameRepo = async (Repo: Repo) => {
    let newName = Repo.name;

    modal.confirm({
      title: t('resources:repos.renameTitle'),
      content: (
        <div>
          <Typography.Paragraph>
            {t('resources:repos.renameMessage', { name: Repo.name })}
          </Typography.Paragraph>
          <Input
            defaultValue={Repo.name}
            placeholder={t('resources:repos.newRepoName')}
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
          showMessage('error', t('resources:repos.emptyNameError'));
          return Promise.reject();
        }

        if (trimmedName === Repo.name) {
          showMessage('info', t('resources:repos.nameUnchanged'));
          return Promise.reject();
        }

        const existingRepo = teamRepos.find((r) => r.repoName === trimmedName);
        if (existingRepo) {
          showMessage('error', t('resources:repos.nameAlreadyExists', { name: trimmedName }));
          return Promise.reject();
        }

        try {
          await updateRepoNameMutation.mutateAsync({
            teamName: machine.teamName,
            currentRepoName: Repo.name,
            newRepoName: trimmedName,
          });
          showMessage(
            'success',
            t('resources:repos.renameSuccess', { oldName: Repo.name, newName: trimmedName })
          );

          if (onActionComplete) {
            onActionComplete();
          }
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(error, t('resources:repos.renameFailed'));
          showMessage('error', errorMessage);
          return Promise.reject();
        }
      },
    });
  };

  const handleRenameTag = async (Repo: Repo) => {
    let newTag = Repo.repoTag || 'latest';

    modal.confirm({
      title: t('resources:repos.renameTagTitle'),
      content: (
        <div>
          <Typography.Paragraph>
            {t('resources:repos.renameTagMessage', { name: Repo.name, tag: Repo.repoTag })}
          </Typography.Paragraph>
          <Input
            defaultValue={Repo.repoTag}
            placeholder={t('resources:repos.newTagName')}
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
          showMessage('error', t('resources:repos.emptyTagError'));
          return Promise.reject();
        }

        if (trimmedTag === Repo.repoTag) {
          showMessage('info', t('resources:repos.tagUnchanged'));
          return Promise.reject();
        }

        const existingTag = teamRepos.find(
          (r) => r.repoName === Repo.name && r.repoTag === trimmedTag
        );
        if (existingTag) {
          showMessage('error', t('resources:repos.tagAlreadyExists', { tag: trimmedTag }));
          return Promise.reject();
        }

        try {
          await updateRepoTagMutation.mutateAsync({
            teamName: machine.teamName,
            repoName: Repo.name,
            currentTag: Repo.repoTag || 'latest',
            newTag: trimmedTag,
          });
          showMessage(
            'success',
            t('resources:repos.renameTagSuccess', {
              name: Repo.name,
              oldTag: Repo.repoTag,
              newTag: trimmedTag,
            })
          );

          if (onActionComplete) {
            onActionComplete();
          }
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(error, t('resources:repos.renameTagFailed'));
          showMessage('error', errorMessage);
          return Promise.reject();
        }
      },
    });
  };

  const handleDeleteGrandRepo = async (Repo: Repo) => {
    const context = prepareGrandDeletion(Repo.name, Repo.repoTag, teamRepos);

    if (context.status === 'error') {
      const errorKey =
        context.errorCode === 'NOT_FOUND'
          ? 'resources:repos.RepoNotFound'
          : 'resources:repos.notAGrandRepo';
      showMessage('error', t(errorKey));
      return;
    }

    if (context.status === 'blocked') {
      modal.error({
        title: t('resources:repos.cannotDeleteHasClones'),
        content: (
          <div>
            <Typography.Paragraph>
              {t('resources:repos.hasActiveClonesMessage', {
                name: Repo.name,
                count: context.childClones.length,
              })}
            </Typography.Paragraph>
            <RediaccText as="p" weight="bold">
              {t('resources:repos.clonesList')}
            </RediaccText>
            <ul>
              {context.childClones.map((clone) => (
                <li key={clone.repoGuid}>{clone.repoName}</li>
              ))}
            </ul>
            <Typography.Paragraph>{t('resources:repos.deleteOptionsMessage')}</Typography.Paragraph>
          </div>
        ),
        okText: t('common:close'),
      });
      return;
    }

    let confirmationInput = '';

    modal.confirm({
      title: t('resources:repos.deleteGrandConfirmTitle'),
      content: (
        <ModalContent>
          <Alert
            message={t('resources:repos.deleteGrandWarning')}
            description={t('resources:repos.deleteGrandWarningDesc', { name: Repo.name })}
            type="warning"
            showIcon
          />
          <RediaccText weight="bold">
            {t('resources:repos.deleteGrandConfirmPrompt', { name: Repo.name })}
          </RediaccText>
          <ConfirmationInput
            type="text"
            placeholder={Repo.name}
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
        if (confirmationInput !== Repo.name) {
          showMessage('error', t('resources:repos.deleteGrandConfirmationMismatch'));
          return Promise.reject();
        }

        try {
          const grandRepoVault =
            getGrandVaultForOperation(
              context.repoGuid!,
              context.repoGuid,
              teamRepos
            ) || '{}';

          const params: Record<string, unknown> = {
            repo: context.repoGuid,
            grand: context.repoGuid,
          };

          const result = await executeAction({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            addedVia: 'machine-Repo-list-delete-grand',
            machineVault: machine.vaultContent || '{}',
            repoGuid: context.repoGuid,
            vaultContent: grandRepoVault,
            repoNetworkId: context.repoNetworkId,
          });

          if (result.success) {
            if (result.taskId) {
              showMessage('success', t('resources:repos.deleteGrandQueued', { name: Repo.name }));
              if (onQueueItemCreated) {
                onQueueItemCreated(result.taskId, machine.machineName);
              }
              showMessage('success', t('resources:repos.deleteGrandSuccess'));
            } else if (result.isQueued) {
              showMessage('info', t('resources:repos.highestPriorityQueued'));
            }
          } else {
            showMessage('error', result.error || t('resources:repos.deleteGrandFailed'));
            return Promise.reject();
          }
        } catch {
          showMessage('error', t('resources:repos.deleteGrandFailed'));
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
    if (!selectedRepo) return;

    try {
      const RepoData = teamRepos.find(
        (r) => r.repoName === selectedRepo.name && r.repoTag === selectedRepo.repoTag
      );

      if (!RepoData || !RepoData.vaultContent) {
        showMessage('error', t('resources:repos.noCredentialsFound', { name: selectedRepo.name }));
        functionModal.close();
        setSelectedRepo(null);
        return;
      }

      let grandRepoVault = RepoData.vaultContent;
      if (RepoData.grandGuid) {
        const grandRepo = teamRepos.find((r) => r.repoGuid === RepoData.grandGuid);
        if (grandRepo && grandRepo.vaultContent) {
          grandRepoVault = grandRepo.vaultContent;
        }
      }

      const finalParams = { ...functionData.params };
      const repoGuid = RepoData.repoGuid;
      const vaultContent = grandRepoVault;

      if (functionData.function.name === 'fork') {
        const forkTag = getRequiredTag(functionData.params, 'Tag is required for fork');
        if (!forkTag) return;

        let newRepo;
        try {
          newRepo = await createRepoCredential(selectedRepo.name, forkTag);
        } catch {
          showMessage('error', t('resources:repos.failedToCreateRepo'));
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
              repo: RepoData.repoGuid,
              dest: newRepo.repoGuid,
              destinationType: 'machine',
              to: machine.machineName,
              state: selectedRepo.mounted ? 'online' : 'offline',
              grand: RepoData.grandGuid || RepoData.repoGuid || '',
            },
            priority: functionData.priority,
            addedVia: 'machine-Repo-list-fork',
            machineVault: machine.vaultContent || '{}',
            repoGuid: RepoData.repoGuid,
            vaultContent: grandRepoVault,
            repoNetworkId: newRepo.repoNetworkId,
            repoNetworkMode: newRepo.repoNetworkMode,
            repoTag: newRepo.repoTag,
          });

          closeModalAndReset();

          if (result.success) {
            if (result.taskId) {
              showMessage(
                'success',
                t('resources:repos.forkStarted', { dest: `${selectedRepo.name}:${forkTag}` })
              );
              if (onQueueItemCreated) onQueueItemCreated(result.taskId, machine.machineName);
            } else if (result.isQueued) {
              showMessage('info', t('resources:repos.highestPriorityQueued'));
            }
          } else {
            throw new Error(result.error || 'Failed to fork Repo');
          }
        } catch {
          showMessage('error', t('resources:repos.failedToForkRepo'));
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
          newRepo = await createRepoCredential(selectedRepo.name, deployTag);
        } catch {
          showMessage('error', t('resources:repos.failedToCreateRepo'));
          closeModalAndReset();
          return;
        }

        const createdTaskIds: string[] = [];
        for (const targetMachine of machinesArray) {
          const destinationMachine = teamMachines.find((m) => m.machineName === targetMachine);
          if (!destinationMachine) {
            showMessage(
              'error',
              t('resources:repos.destinationMachineNotFound', { machine: targetMachine })
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
                dest: newRepo.repoGuid,
                repo: RepoData.repoGuid,
                grand: RepoData.grandGuid || RepoData.repoGuid || '',
                state: selectedRepo.mounted ? 'online' : 'offline',
              },
              priority: functionData.priority,
              addedVia: 'machine-Repo-list',
              machineVault: machine.vaultContent || '{}',
              destinationMachineVault: destinationMachine.vaultContent || '{}',
              repoGuid,
              vaultContent,
              repoNetworkId: newRepo.repoNetworkId,
              repoNetworkMode: newRepo.repoNetworkMode,
              repoTag: newRepo.repoTag,
            });
            if (result.success && result.taskId) createdTaskIds.push(result.taskId);
          } catch {
            showMessage('error', t('resources:repos.failedToDeployTo', { machine: targetMachine }));
          }
        }

        closeModalAndReset();
        showMultiTargetSummary(createdTaskIds, machinesArray.length, {
          success: 'resources:repos.deploymentQueued',
          partial: 'resources:repos.deploymentPartialSuccess',
          allFailed: 'resources:repos.allDeploymentsFailed',
        });
        return;
      }

      if (functionData.function.name === 'backup' && functionData.params.storages) {
        if (!canBackupToStorage(RepoData).canBackup) {
          showMessage('error', t('resources:repos.cannotBackupForkToStorage'));
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
              t('resources:repos.destinationStorageNotFound', { storage: targetStorage })
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
                dest: RepoData.repoGuid,
                repo: RepoData.repoGuid,
                grand: RepoData.grandGuid || RepoData.repoGuid || '',
                state: selectedRepo.mounted ? 'online' : 'offline',
              },
              priority: functionData.priority,
              addedVia: 'machine-Repo-list',
              machineVault: machine.vaultContent || '{}',
              destinationStorageVault: destinationStorage.vaultContent || '{}',
              repoGuid,
              vaultContent,
              repoNetworkId: RepoData.repoNetworkId,
              repoNetworkMode: RepoData.repoNetworkMode,
              repoTag: RepoData.repoTag,
            });
            if (result.success && result.taskId) createdTaskIds.push(result.taskId);
          } catch {
            showMessage('error', t('resources:repos.failedToBackupTo', { storage: targetStorage }));
          }
        }

        closeModalAndReset();
        showMultiTargetSummary(createdTaskIds, storagesArray.length, {
          success: 'resources:repos.backupQueued',
          partial: 'resources:repos.backupPartialSuccess',
          allFailed: 'resources:repos.allBackupsFailed',
        });
        return;
      }

      if (functionData.function.name === 'pull') {
        finalParams.repo = RepoData.repoGuid;
        finalParams.grand = RepoData.grandGuid || RepoData.repoGuid || '';
      }

      const result = await executeAction({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: functionData.function.name,
        params: finalParams,
        priority: functionData.priority,
        addedVia: 'machine-Repo-list',
        machineVault: machine.vaultContent || '{}',
        repoGuid,
        vaultContent,
        repoNetworkId: RepoData.repoNetworkId,
        repoNetworkMode: RepoData.repoNetworkMode,
        repoTag: RepoData.repoTag,
      });

      functionModal.close();
      setSelectedRepo(null);

      if (result.success) {
        if (result.taskId) {
          showMessage('success', t('resources:repos.queueItemCreated'));
          if (onQueueItemCreated) {
            onQueueItemCreated(result.taskId, machine.machineName);
          }
        } else if (result.isQueued) {
          showMessage('info', t('resources:repos.highestPriorityQueued'));
        }
      } else {
        throw new Error(result.error || t('resources:repos.failedToCreateQueueItem'));
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('resources:repos.failedToCreateQueueItem');
      showMessage('error', errorMessage);
    }
  };

  const getTableDataSource = (): RepoTableRow[] => {
    const tableData: RepoTableRow[] = [];

    groupedRepos.forEach((group) => {
      if (group.grandTag) {
        tableData.push({
          ...group.grandTag,
          key: `repo-${group.name}-${group.grandTag.repoTag || 'latest'}`,
        } as RepoTableRow);
      }

      group.forkTags.forEach((fork) => {
        tableData.push({
          ...fork,
          key: `repo-${fork.name}-${fork.repoTag || 'latest'}`,
        } as RepoTableRow);
      });
    });

    return tableData;
  };

  const columns: ColumnsType<RepoTableRow> = [
    repoStatusColumn,
    repoNameColumn,
    createActionColumn<RepoTableRow>({
      title: t('common:table.actions'),
      width: DESIGN_TOKENS.DIMENSIONS.CARD_WIDTH,
      fixed: 'end',
      renderActions: (record) => (
        <RepoActionsMenu
          record={record}
          teamRepos={teamRepos}
          machine={machine}
          userEmail={userEmail}
          containersData={containersData}
          isExecuting={isExecuting}
          onQuickAction={handleQuickAction}
          onRunFunction={handleRunFunction}
          onPromoteToGrand={handlePromoteToGrand}
          onDeleteFork={handleDeleteFork}
          onRenameTag={handleRenameTag}
          onRenameRepo={handleRenameRepo}
          onDeleteGrandRepo={handleDeleteGrandRepo}
          onRepoClick={onRepoClick}
          onCreateRepo={onCreateRepo}
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
          tip={t('resources:repos.fetchingRepos') as string}
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
            <Tooltip title={t('common:actions.retry')}>
              <Button
                size="small"
                onClick={handleRefresh}
                data-testid="machine-repo-list-retry"
                aria-label={t('common:actions.retry')}
              />
            </Tooltip>
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
            tip={t('common:general.refreshing') as string}
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
              <InfoTag data-testid="machine-repo-list-team-tag">{machine.teamName}</InfoTag>
              <InfoTag data-testid="machine-repo-list-bridge-tag">{machine.bridgeName}</InfoTag>
              {machine.regionName && (
                <InfoTag data-testid="machine-repo-list-region-tag">{machine.regionName}</InfoTag>
              )}
              <InfoTag data-testid="machine-repo-list-queue-tag">
                {machine.queueCount} {t('machines:queueItems')}
              </InfoTag>
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

      <RepoTableComponent
        columns={columns}
        dataSource={getTableDataSource()}
        rowKey={(record: RepoTableRow) =>
          record.key || `${record.name}-${record.repoTag || 'latest'}`
        }
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
        data-testid="machine-repo-list-table"
        rowClassName={(record: RepoTableRow) => {
          const repoData = teamRepos.find(
            (r) => r.repoName === record.name && r.repoTag === record.repoTag
          );
          const classes = ['Repo-row'];
          if (repoData && coreIsFork(repoData)) {
            classes.push('Repo-fork-row');
          }
          if (highlightedRepo?.name === record.name) {
            classes.push('Repo-row--highlighted');
          }
          return classes.join(' ');
        }}
        locale={{
          emptyText: t('resources:repos.noRepos'),
        }}
        onRow={(record: RepoTableRow) => ({
          onClick: (e: React.MouseEvent<HTMLElement>) => {
            const target = e.target as HTMLElement;
            if (target.closest('button') || target.closest('.ant-dropdown')) {
              return;
            }

            navigate(`/machines/${machine.machineName}/repos/${record.name}/containers`, {
              state: { machine, Repo: record },
            });
          },
        })}
      />

      {systemContainers.length > 0 && !hideSystemInfo && (
        <S.SystemContainersWrapper data-testid="machine-repo-list-system-containers">
          <S.SystemContainersTitle
            as={Typography.Title}
            level={5}
            data-testid="machine-repo-list-system-containers-title"
          >
            {t('resources:repos.systemContainers')}
          </S.SystemContainersTitle>
          <SystemTableComponent
            columns={systemContainerColumns}
            dataSource={systemContainers}
            rowKey="id"
            size="small"
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
          selectedRepo && (
            <RediaccStack direction="vertical" gap="sm" fullWidth>
              <Space>
                <RediaccText>{t('resources:repos.Repo')}:</RediaccText>
                <InlineTag>{selectedRepo.name}</InlineTag>
                <RediaccText>•</RediaccText>
                <RediaccText>{t('machines:machine')}:</RediaccText>
                <MachineTag>{machine.machineName}</MachineTag>
              </Space>
              {selectedFunction === 'push' &&
                (() => {
                  const currentRepoData = teamRepos.find(
                    (r) => r.repoName === selectedRepo.name && r.repoTag === selectedRepo.repoTag
                  );
                  if (currentRepoData?.parentGuid) {
                    const parentRepo = teamRepos.find(
                      (r) => r.repoGuid === currentRepoData.parentGuid
                    );
                    if (parentRepo) {
                      return (
                        <Space>
                          <SmallText color="secondary">
                            {t('resources:repos.parentRepo', { defaultValue: 'Parent Repo' })}:
                          </SmallText>
                          <InlineTag>{parentRepo.repoName}</InlineTag>
                          <SmallText color="secondary">→</SmallText>
                          <SmallText color="secondary">{t('common:current')}:</SmallText>
                          <InlineTag>{selectedRepo.name}</InlineTag>
                        </Space>
                      );
                    }
                  }
                  return null;
                })()}
            </RediaccStack>
          )
        }
        allowedCategories={['Repo', 'backup', 'network']}
        loading={isExecuting}
        showMachineSelection={false}
        teamName={machine.teamName}
        hiddenParams={['repo', 'grand', 'state']}
        defaultParams={{
          repo: (() => {
            const repo = teamRepos.find(
              (r) => r.repoName === selectedRepo?.name && r.repoTag === selectedRepo?.repoTag
            );
            return repo?.repoGuid || '';
          })(),
          grand:
            teamRepos.find(
              (r) => r.repoName === selectedRepo?.name && r.repoTag === selectedRepo?.repoTag
            )?.grandGuid || '',
          ...((selectedFunction === 'backup' ||
            selectedFunction === 'push' ||
            selectedFunction === 'deploy' ||
            selectedFunction === 'fork') &&
          selectedRepo
            ? {
                state: selectedRepo.mounted ? 'online' : 'offline',
              }
            : {}),
        }}
        initialParams={{
          ...((selectedFunction === 'fork' || selectedFunction === 'deploy') && selectedRepo
            ? {
                tag: new Date().toISOString().slice(0, 19).replace('T', '-').replace(/:/g, '-'),
              }
            : {}),
        }}
        preselectedFunction={selectedFunction || undefined}
        currentMachineName={machine.machineName}
        additionalContext={
          selectedFunction === 'push' && selectedRepo
            ? {
                sourceRepo: selectedRepo.name,
                parentRepo: (() => {
                  const currentRepoData = teamRepos.find(
                    (r) => r.repoName === selectedRepo.name && r.repoTag === selectedRepo.repoTag
                  );
                  if (currentRepoData?.parentGuid) {
                    const parentRepo = teamRepos.find(
                      (r) => r.repoGuid === currentRepoData.parentGuid
                    );
                    return parentRepo?.repoName || null;
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
