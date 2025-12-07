import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useUpdateMachineClusterAssignment,
  useUpdateMachineClusterRemoval,
  useUpdateCloneMachineAssignments,
  useUpdateCloneMachineRemovals,
  useUpdateImageMachineAssignment,
} from '@/api/queries/cephMutations';
import { MachineAssignmentService } from '@/features/ceph/services';
import type { Machine } from '@/types';

export interface CloneIdentifier {
  cloneName: string;
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
}

export interface PoolIdentifier {
  poolName: string;
  teamName: string;
}

export interface AssignmentResult {
  success: boolean;
  message?: string;
  failedMachines?: string[];
}

export const useMachineAssignment = (teamName?: string) => {
  const { t } = useTranslation(['ceph', 'machines']);

  // Mutations
  const clusterAssignMutation = useUpdateMachineClusterAssignment();
  const clusterRemoveMutation = useUpdateMachineClusterRemoval();
  const cloneAssignMutation = useUpdateCloneMachineAssignments();
  const cloneRemoveMutation = useUpdateCloneMachineRemovals();
  const imageReassignMutation = useUpdateImageMachineAssignment();

  // Assign machines to cluster
  const assignToCluster = useCallback(
    async (machineNames: string[], clusterName: string): Promise<AssignmentResult> => {
      if (!teamName) {
        return {
          success: false,
          message: t('machines:errors.teamRequired'),
        };
      }

      try {
        // Process machines one by one for cluster assignment
        const results = await Promise.allSettled(
          machineNames.map((machineName) =>
            clusterAssignMutation.mutateAsync({
              teamName,
              machineName,
              clusterName,
            })
          )
        );

        const failedMachines = results
          .map((result, index) => (result.status === 'rejected' ? machineNames[index] : null))
          .filter(Boolean) as string[];

        if (failedMachines.length === 0) {
          return {
            success: true,
            message: t('machines:bulkOperations.assignmentSuccess', { count: machineNames.length }),
          };
        } else if (failedMachines.length < machineNames.length) {
          return {
            success: false,
            message: t('machines:bulkOperations.assignmentPartial', {
              success: machineNames.length - failedMachines.length,
              total: machineNames.length,
            }),
            failedMachines,
          };
        } else {
          return {
            success: false,
            message: t('machines:bulkOperations.assignmentFailed'),
            failedMachines,
          };
        }
      } catch (error) {
        return {
          success: false,
          message: error instanceof Error ? error.message : t('common:errors.unknown'),
        };
      }
    },
    [teamName, clusterAssignMutation, t]
  );

  // Assign machines to clone
  const assignToClone = useCallback(
    async (machineNames: string[], cloneInfo: CloneIdentifier): Promise<AssignmentResult> => {
      try {
        await cloneAssignMutation.mutateAsync({
          ...cloneInfo,
          machineNames: machineNames.join(','),
        });

        return {
          success: true,
          message: t('ceph:clones.machinesAssignedSuccess'),
        };
      } catch (error) {
        return {
          success: false,
          message: error instanceof Error ? error.message : t('common:errors.unknown'),
        };
      }
    },
    [cloneAssignMutation, t]
  );

  // Remove machines from cluster
  const removeFromCluster = useCallback(
    async (machineNames: string[]): Promise<AssignmentResult> => {
      if (!teamName) {
        return {
          success: false,
          message: t('machines:errors.teamRequired'),
        };
      }

      try {
        const results = await Promise.allSettled(
          machineNames.map((machineName) =>
            clusterRemoveMutation.mutateAsync({
              teamName,
              machineName,
            })
          )
        );

        const failedMachines = results
          .map((result, index) => (result.status === 'rejected' ? machineNames[index] : null))
          .filter(Boolean) as string[];

        if (failedMachines.length === 0) {
          return {
            success: true,
            message: t('machines:bulkOperations.removalSuccess', { count: machineNames.length }),
          };
        } else {
          return {
            success: false,
            message: t('machines:bulkOperations.removalPartial'),
            failedMachines,
          };
        }
      } catch (error) {
        return {
          success: false,
          message: error instanceof Error ? error.message : t('common:errors.unknown'),
        };
      }
    },
    [teamName, clusterRemoveMutation, t]
  );

  // Remove machines from clone
  const removeFromClone = useCallback(
    async (machineNames: string[], cloneInfo: CloneIdentifier): Promise<AssignmentResult> => {
      try {
        await cloneRemoveMutation.mutateAsync({
          ...cloneInfo,
          machineNames: machineNames.join(','),
        });

        return {
          success: true,
          message: t('ceph:clones.machinesRemovedSuccess'),
        };
      } catch (error) {
        return {
          success: false,
          message: error instanceof Error ? error.message : t('common:errors.unknown'),
        };
      }
    },
    [cloneRemoveMutation, t]
  );

  // Reassign image to different machine
  const reassignImage = useCallback(
    async (
      imageName: string,
      newMachineName: string,
      poolInfo: PoolIdentifier
    ): Promise<AssignmentResult> => {
      try {
        await imageReassignMutation.mutateAsync({
          imageName,
          poolName: poolInfo.poolName,
          teamName: poolInfo.teamName,
          newMachineName,
        });

        return {
          success: true,
          message: t('ceph:images.reassignmentSuccess'),
        };
      } catch (error) {
        return {
          success: false,
          message: error instanceof Error ? error.message : t('common:errors.unknown'),
        };
      }
    },
    [imageReassignMutation, t]
  );

  // Note: getAssignmentStatus removed as it violated hooks rules
  // Users should call useMachineAssignmentStatus directly in their components

  // Helper to check if machines can be assigned
  const canAssignMachines = useCallback(
    (machines: Machine[], targetType: 'cluster' | 'image' | 'clone'): boolean => {
      return machines.every((machine) =>
        MachineAssignmentService.canAssignMachine(machine, targetType)
      );
    },
    []
  );

  // Loading states
  const isAssigning = useMemo(
    () =>
      clusterAssignMutation.isPending ||
      cloneAssignMutation.isPending ||
      imageReassignMutation.isPending,
    [
      clusterAssignMutation.isPending,
      cloneAssignMutation.isPending,
      imageReassignMutation.isPending,
    ]
  );

  const isRemoving = useMemo(
    () => clusterRemoveMutation.isPending || cloneRemoveMutation.isPending,
    [clusterRemoveMutation.isPending, cloneRemoveMutation.isPending]
  );

  return {
    // Assignment operations
    assignToCluster,
    assignToClone,
    removeFromCluster,
    removeFromClone,
    reassignImage,

    // Status checking
    canAssignMachines,

    // Loading states
    isAssigning,
    isRemoving,
    isLoading: isAssigning || isRemoving,
  };
};
