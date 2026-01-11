import { useCallback } from 'react';
import type {
  useCreateStorage,
  useDeleteStorage,
  useUpdateStorageName,
  useUpdateStorageVault,
} from '@/api/api-hooks.generated';
import type { DynamicQueueActionParams, QueueActionResult } from '@/services/queue';
import type { Machine } from '@/types';
import { confirmDelete } from '@/utils/confirmations';
import { showMessage } from '@/utils/messages';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import type { GetTeamStorages_ResultSet1 } from '@rediacc/shared/types';
import type { OrganizationDropdownData } from '@rediacc/shared/types';
import type { StorageFunctionData } from '../types';
import type { HookAPI } from 'antd/es/modal/useModal';

interface Team {
  teamName: string;
  vaultContent?: string | null;
}

interface UseStorageHandlersParams {
  t: TypedTFunction;
  modal: HookAPI;
  execute: <T>(
    fn: () => Promise<T>,
    options?: { skipSuccessMessage?: boolean }
  ) => Promise<{ success: boolean; data?: T; error?: string }>;
  deleteStorageMutation: ReturnType<typeof useDeleteStorage>;
  createStorageMutation: ReturnType<typeof useCreateStorage>;
  updateStorageNameMutation: ReturnType<typeof useUpdateStorageName>;
  updateStorageVaultMutation: ReturnType<typeof useUpdateStorageVault>;
  refetchStorage: () => void;
  closeUnifiedModal: () => void;
  unifiedModalMode: 'create' | 'edit' | 'view' | 'vault';
  currentResource: (GetTeamStorages_ResultSet1 & Record<string, unknown>) | null;
  dropdownData: OrganizationDropdownData | undefined;
  machines: Machine[];
  storages: GetTeamStorages_ResultSet1[];
  teams: Team[];
  executeDynamic: (
    functionName: BridgeFunctionName,
    params: Omit<DynamicQueueActionParams, 'functionName'>
  ) => Promise<QueueActionResult>;
  openQueueTrace: (taskId: string, machineName: string) => void;
}

export const useStorageHandlers = ({
  t,
  modal,
  execute,
  deleteStorageMutation,
  createStorageMutation,
  updateStorageNameMutation,
  updateStorageVaultMutation,
  refetchStorage,
  closeUnifiedModal,
  unifiedModalMode,
  currentResource,
  dropdownData,
  machines,
  storages,
  teams,
  executeDynamic,
  openQueueTrace,
}: UseStorageHandlersParams) => {
  const handleDeleteStorage = useCallback(
    (storage: GetTeamStorages_ResultSet1) => {
      confirmDelete({
        modal,
        t,
        resourceType: 'storage',
        resourceName: storage.storageName ?? '',
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
      const storageData = data as {
        storageName?: string;
        teamName?: string;
        vaultContent?: string;
      };
      await execute(
        async () => {
          if (unifiedModalMode === 'create') {
            if (!storageData.storageName || !storageData.teamName) {
              throw new Error('Storage name and team name are required');
            }
            await createStorageMutation.mutateAsync({
              storageName: storageData.storageName,
              teamName: storageData.teamName,
              vaultContent: storageData.vaultContent ?? '{}',
            });
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
                storageName: newName ?? currentName,
                vaultContent: vaultData,
                vaultVersion: (currentResource.vaultVersion ?? 0) + 1,
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
      unifiedModalMode,
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

  const findMachineEntry = useCallback(
    (selectedMachine: string | undefined) => {
      if (!selectedMachine || !currentResource) return null;

      const teamEntry = dropdownData?.machinesByTeam.find(
        (team) => team.teamName === currentResource.teamName
      );
      return teamEntry?.machines.find((machine) => machine.value === selectedMachine) ?? null;
    },
    [currentResource, dropdownData]
  );

  const addBackupPullVaults = useCallback(
    (
      queuePayload: Omit<DynamicQueueActionParams, 'functionName'>,
      functionData: StorageFunctionData
    ) => {
      if (functionData.function.name !== 'backup_pull') return;

      const { sourceType, from: sourceIdentifier } = functionData.params;

      if (sourceType === 'machine' && typeof sourceIdentifier === 'string') {
        const sourceMachine = machines.find((m) => m.machineName === sourceIdentifier);
        if (sourceMachine?.vaultContent) {
          queuePayload.sourceMachineVault = sourceMachine.vaultContent;
        }
      } else if (sourceType === 'storage' && typeof sourceIdentifier === 'string') {
        const sourceStorage = storages.find((s) => s.storageName === sourceIdentifier);
        if (sourceStorage?.vaultContent) {
          queuePayload.sourceStorageVault = sourceStorage.vaultContent;
        }
      }
    },
    [machines, storages]
  );

  const handleStorageFunctionSelected = useCallback(
    async (functionData: StorageFunctionData) => {
      if (!currentResource) return;

      const machineEntry = findMachineEntry(functionData.selectedMachine);
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
        addedVia: 'storage-table',
        teamVault:
          teams.find((team) => team.teamName === currentResource.teamName)?.vaultContent ?? '{}',
        storageName: currentResource.storageName ?? '',
        storageVault: currentResource.vaultContent ?? '{}',
        machineVault: selectedMachine?.vaultContent ?? '{}',
      };

      addBackupPullVaults(queuePayload, functionData);

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
        showMessage('success', t('storage.queueItemCreated'));
        openQueueTrace(result.taskId, machineEntry.value);
      } else if (result.isQueued) {
        showMessage(
          'info',
          t('resources:messages.highestPriorityQueued', { resourceType: 'storage' })
        );
      }
    },
    [
      addBackupPullVaults,
      closeUnifiedModal,
      currentResource,
      executeDynamic,
      findMachineEntry,
      machines,
      openQueueTrace,
      t,
      teams,
    ]
  );

  return {
    handleDeleteStorage,
    handleUnifiedModalSubmit,
    handleUnifiedVaultUpdate,
    handleStorageFunctionSelected,
  };
};
