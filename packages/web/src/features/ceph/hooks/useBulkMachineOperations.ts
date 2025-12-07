import { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useMachineAssignment } from '@/features/ceph/hooks/useMachineAssignment';
import type { CloneIdentifier } from '@/features/ceph/hooks/useMachineAssignment';
import { MachineValidationService, type BulkValidationResult } from '@/features/ceph/services';
import type { Machine } from '@/types';
import { showMessage } from '@/utils/messages';

export interface BulkOperationProgress {
  total: number;
  completed: number;
  failed: number;
  isProcessing: boolean;
}

export interface BulkOperationResult {
  success: boolean;
  successfulMachines: string[];
  failedMachines: string[];
  errors: Record<string, string>;
}

type LastOperationContext =
  | {
      type: 'assign-cluster';
      machines: string[];
      clusterName: string;
    }
  | {
      type: 'assign-clone';
      machines: string[];
      cloneInfo: CloneIdentifier;
    }
  | {
      type: 'remove-cluster';
      machines: string[];
    }
  | {
      type: 'remove-clone';
      machines: string[];
      cloneInfo?: CloneIdentifier;
    };

export const useBulkMachineOperations = (teamName?: string) => {
  const { t } = useTranslation(['machines', 'ceph']);
  const [selectedMachines, setSelectedMachines] = useState<Set<string>>(new Set());
  const [operationProgress, setOperationProgress] = useState<BulkOperationProgress>({
    total: 0,
    completed: 0,
    failed: 0,
    isProcessing: false,
  });
  const [lastOperationResult, setLastOperationResult] = useState<BulkOperationResult | null>(null);
  const [lastOperationContext, setLastOperationContext] = useState<LastOperationContext | null>(
    null
  );

  const { assignToCluster, assignToClone, removeFromCluster, removeFromClone } =
    useMachineAssignment(teamName);

  // Selection management
  const selectMachines = useCallback((machineNames: string[]) => {
    setSelectedMachines((prev) => {
      const newSet = new Set(prev);
      machineNames.forEach((name) => newSet.add(name));
      return newSet;
    });
  }, []);

  const deselectMachines = useCallback((machineNames: string[]) => {
    setSelectedMachines((prev) => {
      const newSet = new Set(prev);
      machineNames.forEach((name) => newSet.delete(name));
      return newSet;
    });
  }, []);

  const selectAll = useCallback((machines: Machine[]) => {
    const machineNames = machines.map((m) => m.machineName);
    setSelectedMachines(new Set(machineNames));
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedMachines(new Set());
  }, []);

  const toggleSelection = useCallback((machineName: string) => {
    setSelectedMachines((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(machineName)) {
        newSet.delete(machineName);
      } else {
        newSet.add(machineName);
      }
      return newSet;
    });
  }, []);

  // Pre-validate selection
  const validateSelection = useCallback(
    (machines: Machine[], targetType: 'cluster' | 'image' | 'clone'): BulkValidationResult => {
      return MachineValidationService.validateBulkAssignment(machines, targetType);
    },
    []
  );

  // Execute bulk assignment
  const executeBulkAssignment = useCallback(
    async (
      targetType: 'cluster' | 'image' | 'clone',
      targetResource: string,
      cloneInfo?: {
        snapshotName: string;
        imageName: string;
        poolName: string;
      }
    ): Promise<BulkOperationResult> => {
      if (!teamName) {
        showMessage('error', t('machines:errors.teamRequired'));
        return {
          success: false,
          successfulMachines: [],
          failedMachines: Array.from(selectedMachines),
          errors: {},
        };
      }

      const machineNames = Array.from(selectedMachines);
      if (machineNames.length === 0) {
        showMessage('warning', t('machines:validation.noMachinesSelected'));
        return {
          success: false,
          successfulMachines: [],
          failedMachines: [],
          errors: {},
        };
      }

      // Reset progress
      setOperationProgress({
        total: machineNames.length,
        completed: 0,
        failed: 0,
        isProcessing: true,
      });

      const successfulMachines: string[] = [];
      const failedMachines: string[] = [];
      const errors: Record<string, string> = {};

      try {
        if (targetType === 'cluster') {
          // Batch process cluster assignments
          const batchSize = 5;
          for (let i = 0; i < machineNames.length; i += batchSize) {
            const batch = machineNames.slice(i, i + batchSize);
            const result = await assignToCluster(batch, targetResource);

            if (result.success) {
              successfulMachines.push(...batch);
            } else {
              failedMachines.push(...(result.failedMachines || batch));
              batch.forEach((machine) => {
                errors[machine] = result.message || t('common:errors.unknown');
              });
            }

            setOperationProgress((prev) => ({
              ...prev,
              completed: successfulMachines.length,
              failed: failedMachines.length,
            }));
          }
        } else if (targetType === 'clone' && cloneInfo) {
          // Clone assignment is done in one batch
          const result = await assignToClone(machineNames, {
            cloneName: targetResource,
            ...cloneInfo,
            teamName,
          });

          if (result.success) {
            successfulMachines.push(...machineNames);
          } else {
            failedMachines.push(...(result.failedMachines || machineNames));
            machineNames.forEach((machine) => {
              errors[machine] = result.message || t('common:errors.unknown');
            });
          }

          setOperationProgress((prev) => ({
            ...prev,
            completed: successfulMachines.length,
            failed: failedMachines.length,
          }));
        }

        const operationResult: BulkOperationResult = {
          success: failedMachines.length === 0,
          successfulMachines,
          failedMachines,
          errors,
        };

        setLastOperationResult(operationResult);
        setLastOperationContext(null);
        if (successfulMachines.length > 0) {
          if (targetType === 'cluster') {
            setLastOperationContext({
              type: 'assign-cluster',
              clusterName: targetResource,
              machines: [...successfulMachines],
            });
          } else if (targetType === 'clone' && cloneInfo && teamName) {
            setLastOperationContext({
              type: 'assign-clone',
              cloneInfo: {
                ...cloneInfo,
                cloneName: targetResource,
                teamName,
              },
              machines: [...successfulMachines],
            });
          } else {
            setLastOperationContext(null);
          }
        } else {
          setLastOperationContext(null);
        }

        // Show appropriate message
        if (operationResult.success) {
          showMessage(
            'success',
            t('machines:bulkOperations.assignmentSuccess', {
              count: successfulMachines.length,
            })
          );
        } else if (successfulMachines.length > 0) {
          showMessage(
            'warning',
            t('machines:bulkOperations.assignmentPartial', {
              success: successfulMachines.length,
              total: machineNames.length,
            })
          );
        } else {
          showMessage('error', t('machines:bulkOperations.assignmentFailed'));
        }

        // Clear selection if all succeeded
        if (operationResult.success) {
          clearSelection();
        }

        return operationResult;
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : t('common:errors.unknown');
        showMessage('error', errorMessage);
        setLastOperationContext(null);

        return {
          success: false,
          successfulMachines: [],
          failedMachines: machineNames,
          errors: Object.fromEntries(machineNames.map((name) => [name, errorMessage])),
        };
      } finally {
        setOperationProgress((prev) => ({
          ...prev,
          isProcessing: false,
        }));
      }
    },
    [teamName, selectedMachines, assignToCluster, assignToClone, clearSelection, t]
  );

  // Execute bulk removal
  const executeBulkRemoval = useCallback(
    async (
      sourceType: 'cluster' | 'clone',
      cloneInfo?: {
        cloneName: string;
        snapshotName: string;
        imageName: string;
        poolName: string;
      }
    ): Promise<BulkOperationResult> => {
      if (!teamName) {
        showMessage('error', t('machines:errors.teamRequired'));
        return {
          success: false,
          successfulMachines: [],
          failedMachines: Array.from(selectedMachines),
          errors: {},
        };
      }

      const machineNames = Array.from(selectedMachines);
      if (machineNames.length === 0) {
        showMessage('warning', t('machines:validation.noMachinesSelected'));
        return {
          success: false,
          successfulMachines: [],
          failedMachines: [],
          errors: {},
        };
      }

      setOperationProgress({
        total: machineNames.length,
        completed: 0,
        failed: 0,
        isProcessing: true,
      });

      try {
        let result;
        if (sourceType === 'cluster') {
          result = await removeFromCluster(machineNames);
        } else if (sourceType === 'clone' && cloneInfo) {
          result = await removeFromClone(machineNames, {
            ...cloneInfo,
            teamName,
          });
        } else {
          throw new Error(t('machines:errors.invalidOperation'));
        }

        const operationResult: BulkOperationResult = {
          success: result.success,
          successfulMachines: result.success ? machineNames : [],
          failedMachines: result.failedMachines || (result.success ? [] : machineNames),
          errors: result.success
            ? {}
            : Object.fromEntries(
                machineNames.map((name) => [name, result.message || t('common:errors.unknown')])
              ),
        };

        setLastOperationResult(operationResult);

        if (operationResult.success) {
          showMessage(
            'success',
            t('machines:bulkOperations.removalSuccess', {
              count: machineNames.length,
            })
          );
          clearSelection();
        }

        return operationResult;
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : t('common:errors.unknown');
        showMessage('error', errorMessage);
        setLastOperationContext(null);

        return {
          success: false,
          successfulMachines: [],
          failedMachines: machineNames,
          errors: Object.fromEntries(machineNames.map((name) => [name, errorMessage])),
        };
      } finally {
        setOperationProgress((prev) => ({
          ...prev,
          isProcessing: false,
        }));
      }
    },
    [teamName, selectedMachines, removeFromCluster, removeFromClone, clearSelection, t]
  );

  // Rollback last operation
  const rollbackLastOperation = useCallback(async (): Promise<boolean> => {
    if (!lastOperationContext || lastOperationContext.machines.length === 0) {
      showMessage('warning', t('machines:bulkOperations.nothingToRollback'));
      return false;
    }

    try {
      switch (lastOperationContext.type) {
        case 'assign-cluster': {
          const result = await removeFromCluster(lastOperationContext.machines);
          if (result.success) {
            showMessage(
              'success',
              t('machines:bulkOperations.rollbackSuccess', {
                count: lastOperationContext.machines.length,
              })
            );
            setLastOperationContext(null);
            setLastOperationResult(null);
            return true;
          }

          showMessage('error', result.message || t('machines:bulkOperations.rollbackFailure'));
          return false;
        }
        case 'assign-clone': {
          const result = await removeFromClone(
            lastOperationContext.machines,
            lastOperationContext.cloneInfo
          );
          if (result.success) {
            showMessage(
              'success',
              t('machines:bulkOperations.rollbackSuccess', {
                count: lastOperationContext.machines.length,
              })
            );
            setLastOperationContext(null);
            setLastOperationResult(null);
            return true;
          }

          showMessage('error', result.message || t('machines:bulkOperations.rollbackFailure'));
          return false;
        }
        default: {
          showMessage('info', t('machines:bulkOperations.rollbackUnavailable'));
          return false;
        }
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : t('common:errors.unknown');
      showMessage('error', errorMessage);
      return false;
    }
  }, [lastOperationContext, removeFromCluster, removeFromClone, t]);

  // Computed values
  const selectedCount = useMemo(() => selectedMachines.size, [selectedMachines]);
  const hasSelection = useMemo(() => selectedCount > 0, [selectedCount]);
  const selectedMachineNames = useMemo(() => Array.from(selectedMachines), [selectedMachines]);

  return {
    // Selection management
    selectedMachines: selectedMachineNames,
    selectedCount,
    hasSelection,
    selectMachines,
    deselectMachines,
    selectAll,
    clearSelection,
    toggleSelection,

    // Operations
    validateSelection,
    executeBulkAssignment,
    executeBulkRemoval,
    rollbackLastOperation,

    // Progress tracking
    operationProgress,
    lastOperationResult,
    isProcessing: operationProgress.isProcessing,
  };
};
