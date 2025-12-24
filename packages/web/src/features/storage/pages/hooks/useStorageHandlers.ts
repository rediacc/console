import { useCallback } from 'react';
import type { GetMachines_Result } from '@/api/queries/machines';
import type {
  GetTeamStorages_ResultSet1,
  useCreateStorage,
  useDeleteStorage,
  useUpdateStorageName,
  useUpdateStorageVault,
} from '@/api/queries/storage';
import type { DropdownData } from '@/api/queries/useDropdownData';
import type { QueueActionParams } from '@/services/queue';
import { confirmDelete } from '@/utils/confirmations';
import { showMessage } from '@/utils/messages';
import type { StorageFunctionData } from '../types';
import type { HookAPI } from 'antd/es/modal/useModal';
import type { TFunction } from 'i18next';

interface Team {
  teamName: string;
  vaultContent?: string;
}

interface UseStorageHandlersParams {
  t: TFunction;
  modal: HookAPI;
  execute: <T>(fn: () => Promise<T>, options?: { skipSuccessMessage?: boolean }) => Promise<T>;
  deleteStorageMutation: ReturnType<typeof useDeleteStorage>;
  createStorageMutation: ReturnType<typeof useCreateStorage>;
  updateStorageNameMutation: ReturnType<typeof useUpdateStorageName>;
  updateStorageVaultMutation: ReturnType<typeof useUpdateStorageVault>;
  refetchStorage: () => void;
  closeUnifiedModal: () => void;
  unifiedModalMode: 'create' | 'edit' | 'view';
  currentResource: (GetTeamStorages_ResultSet1 & Record<string, unknown>) | null;
  dropdownData: DropdownData | undefined;
  machines: GetMachines_Result[];
  storages: GetTeamStorages_ResultSet1[];
  teams: Team[];
  executeAction: (
    params: QueueActionParams
  ) => Promise<{ success: boolean; taskId?: string; isQueued?: boolean; error?: string }>;
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
  executeAction,
  openQueueTrace,
}: UseStorageHandlersParams) => {
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
      const storageData = data as {
        storageName?: string;
        teamName?: string;
        vaultContent?: string;
      };
      await execute(
        async () => {
          if (unifiedModalMode === 'create') {
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
          openQueueTrace(result.taskId, machineEntry.value);
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
      openQueueTrace,
      storages,
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
