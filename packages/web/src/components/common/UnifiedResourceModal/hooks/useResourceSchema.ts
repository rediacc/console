import { useCallback, useMemo } from 'react';
import { z } from 'zod';
import {
  createBridgeSchema,
  createCloneSchema,
  createClusterSchema,
  createImageSchema,
  createMachineSchema,
  createPoolSchema,
  createRegionSchema,
  createRepositorySchema,
  createSnapshotSchema,
  createStorageSchema,
  createTeamSchema,
} from '@/platform/utils/validation';
import type { ResourceType } from '../index';

type ResourceFormValues = Record<string, unknown>;

interface UseResourceSchemaProps {
  resourceType: ResourceType;
  mode: 'create' | 'edit' | 'vault';
  uiMode: string;
  creationContext?: 'credentials-only' | 'normal';
  existingData?: Record<string, unknown>;
}

export const useResourceSchema = ({
  resourceType,
  mode,
  uiMode,
  creationContext,
  existingData,
}: UseResourceSchemaProps) => {
  // Schema mapping
  const schemaMap = useMemo(
    () => ({
      machine:
        uiMode === 'simple'
          ? z.object({
              machineName: z.string().min(1, 'Machine name is required'),
              teamName: z.string().optional(),
              regionName: z.string().optional(),
              bridgeName: z.string().optional(),
              vaultContent: z.string().optional().default('{}'),
            })
          : createMachineSchema,
      repository: createRepositorySchema,
      storage: createStorageSchema,
      team: createTeamSchema,
      region: createRegionSchema,
      bridge: createBridgeSchema,
      cluster: createClusterSchema,
      pool: createPoolSchema,
      image: createImageSchema,
      snapshot: createSnapshotSchema,
      clone: createCloneSchema,
    }),
    [uiMode]
  );

  const getSchema = useCallback(() => {
    if (mode === 'edit') {
      return z.object({
        [`${resourceType}Name`]: z.string().min(1, `${resourceType} name is required`),
        ...(resourceType === 'machine' && {
          regionName: z.string().optional(),
          bridgeName: z.string().optional(),
        }),
      });
    }

    // For repository creation in credentials-only mode, use simpler validation
    if (resourceType === 'repository' && creationContext === 'credentials-only') {
      return z.object({
        teamName: z.string().min(1, 'Team name is required'),
        repositoryName: z.string().min(1, 'Repository name is required'),
        repositoryGuid: z.string().min(1, 'Repository GUID is required'),
        vaultContent: z.string().optional().default('{}'),
      });
    }

    return schemaMap[resourceType as keyof typeof schemaMap] || z.object({});
  }, [creationContext, mode, resourceType, schemaMap]);

  // Default values factory
  const getDefaultValues = useCallback((): ResourceFormValues => {
    if (mode === 'edit' && existingData) {
      return {
        [`${resourceType}Name`]: existingData[`${resourceType}Name`],
        ...(resourceType === 'machine' && {
          regionName: existingData.regionName,
          bridgeName: existingData.bridgeName,
        }),
        ...(resourceType === 'bridge' && { regionName: existingData.regionName }),
        ...(resourceType === 'pool' && { clusterName: existingData.clusterName }),
        ...(resourceType === 'image' && { poolName: existingData.poolName }),
        ...(resourceType === 'snapshot' && {
          poolName: existingData.poolName,
          imageName: existingData.imageName,
        }),
        ...(resourceType === 'clone' && {
          poolName: existingData.poolName,
          imageName: existingData.imageName,
          snapshotName: existingData.snapshotName,
        }),
        vaultContent: existingData.vaultContent || '{}',
      };
    }

    const baseDefaults: ResourceFormValues = {
      teamName: uiMode === 'simple' ? 'Private Team' : '',
      vaultContent: '{}',
      [`${resourceType}Name`]: '',
    };

    const resourceDefaults = {
      machine: {
        regionName: uiMode === 'simple' ? 'Default Region' : '',
        bridgeName: uiMode === 'simple' ? 'Global Bridges' : '',
        vaultContent: '{}',
      },
      repository: {
        machineName: '',
        size: '',
        repositoryGuid: '', // Add default for repositoryGuid
        vaultContent: '{}',
      },
      team: { teamName: '', vaultContent: '{}' },
      region: { regionName: '', vaultContent: '{}' },
      bridge: { regionName: '', bridgeName: '', vaultContent: '{}' },
      cluster: { clusterName: '', vaultContent: '{}' },
      pool: { clusterName: '', poolName: '', vaultContent: '{}' },
      image: { poolName: '', imageName: '', vaultContent: '{}' },
      snapshot: { poolName: '', imageName: '', snapshotName: '', vaultContent: '{}' },
      clone: { poolName: '', imageName: '', snapshotName: '', cloneName: '', vaultContent: '{}' },
    };

    // Merge existingData to override defaults if provided
    const finalDefaults: ResourceFormValues = {
      ...baseDefaults,
      ...resourceDefaults[resourceType as keyof typeof resourceDefaults],
    };
    if (existingData) {
      Object.keys(existingData).forEach((key) => {
        if (existingData[key] !== undefined) {
          finalDefaults[key] = existingData[key];
        }
      });
    }

    return finalDefaults;
  }, [mode, existingData, resourceType, uiMode]);

  return {
    schemaMap,
    getSchema,
    getDefaultValues,
  };
};
