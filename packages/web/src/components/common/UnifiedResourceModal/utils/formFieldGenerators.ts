import { TFunction } from 'i18next';
import type { FormFieldConfig } from '@/components/common/UnifiedResourceModal/components/ResourceFormWithVault';
import { featureFlags } from '@/config/featureFlags';
import type { ResourceType } from '../index';

type ClusterOption = { clusterName: string };
type PoolOption = { poolName: string; clusterName: string };
type AvailableMachineOption = {
  machineName: string;
  bridgeName: string;
  regionName: string;
  status?: string;
};
type PoolImageOption = { imageName: string };
type SnapshotOption = { snapshotName: string };

interface DropdownData {
  teams?: Array<{ value: string; label: string }>;
  regions?: Array<{ value: string; label: string }>;
  machinesByTeam?: Array<{
    teamName: string;
    machines: Array<{ value: string; label: string }>;
  }>;
}

interface FormFieldGeneratorProps {
  resourceType: ResourceType;
  mode: 'create' | 'edit' | 'vault';
  uiMode: string;
  isExpertMode: boolean;
  isTeamPreselected: boolean;
  existingData?: Record<string, unknown>;
  dropdownData?: DropdownData;
  teamFilter?: string | string[];
  creationContext?: 'credentials-only' | 'normal';
  getFormValue: (field: string) => string | undefined;
  getFilteredBridges: (regionName: string | null) => Array<{ value: string; label: string }>;
  t: TFunction;
}

const getResourceTranslationKey = (resourceType: ResourceType) => {
  const RESOURCE_CONFIG = {
    storage: { key: 'storage' },
    repository: { key: 'repositories' },
    machine: { key: 'machines' },
    team: { key: 'teams' },
    region: { key: 'regions' },
    bridge: { key: 'bridges' },
    cluster: { key: 'clusters' },
    pool: { key: 'pools' },
    image: { key: 'images' },
    snapshot: { key: 'snapshots' },
    clone: { key: 'clones' },
  } as const;

  return RESOURCE_CONFIG[resourceType as keyof typeof RESOURCE_CONFIG]?.key || `${resourceType}s`;
};

const mapToOptions = (items?: Array<{ value: string; label: string }>) =>
  items?.map((item) => ({ value: item.value, label: item.label })) || [];

export const createNameField = (resourceType: ResourceType, t: TFunction): FormFieldConfig => ({
  name: `${resourceType}Name`,
  label: t(`${getResourceTranslationKey(resourceType)}.${resourceType}Name`),
  placeholder: t(
    `${getResourceTranslationKey(resourceType)}.placeholders.enter${resourceType.charAt(0).toUpperCase() + resourceType.slice(1)}Name`
  ),
  required: true,
});

export const createTeamField = (
  dropdownData: DropdownData | undefined,
  t: TFunction
): FormFieldConfig => ({
  name: 'teamName',
  label: t('general.team'),
  placeholder: t('teams.placeholders.selectTeam'),
  required: true,
  type: 'select' as const,
  options: mapToOptions(dropdownData?.teams),
});

export const createRegionField = (
  dropdownData: DropdownData | undefined,
  t: TFunction
): FormFieldConfig => ({
  name: 'regionName',
  label: t('general.region'),
  placeholder: t('regions.placeholders.selectRegion'),
  required: true,
  type: 'select' as const,
  options: mapToOptions(dropdownData?.regions) as Array<{ value: string; label: string }>,
});

export const createBridgeField = (
  getFormValue: (field: string) => string | undefined,
  getFilteredBridges: (regionName: string | null) => Array<{ value: string; label: string }>,
  t: TFunction
): FormFieldConfig => {
  const currentRegion = getFormValue('regionName') ?? null;
  const bridgeOptions = getFilteredBridges(currentRegion);
  return {
    name: 'bridgeName',
    label: t('bridges.bridge'),
    placeholder: currentRegion
      ? t('bridges.placeholders.selectBridge')
      : t('bridges.placeholders.selectRegionFirst'),
    required: true,
    type: 'select' as const,
    options: bridgeOptions,
    disabled: !currentRegion,
  };
};

export const getFormFields = ({
  resourceType,
  mode,
  uiMode,
  isExpertMode,
  isTeamPreselected,
  existingData,
  dropdownData,
  teamFilter,
  creationContext,
  getFormValue,
  getFilteredBridges,
  t,
}: FormFieldGeneratorProps): FormFieldConfig[] => {
  const nameField = createNameField(resourceType, t);

  if (mode === 'edit') {
    if (resourceType === 'machine') {
      const fields = [nameField, createRegionField(dropdownData, t)];
      // Hide bridge field when disableBridge flag is enabled
      // Note: existing bridgeName value is preserved and sent to backend
      if (!featureFlags.isEnabled('disableBridge')) {
        fields.push(createBridgeField(getFormValue, getFilteredBridges, t));
      }
      return fields;
    }
    if (resourceType === 'bridge') return [nameField, createRegionField(dropdownData, t)];
    // For repositories in edit mode, we still need to show the vault fields
    // so users can update credentials if needed
    if (resourceType === 'repository') {
      // Don't include team field in edit mode since team can't be changed
      return [nameField];
    }
    return [nameField];
  }

  if (uiMode === 'simple') {
    const simpleFields = [nameField];

    // For repository creation, we need to include size field and potentially machine selection
    if (resourceType === 'repository') {
      // Check if machine is prefilled
      const isPrefilledMachine = existingData?.prefilledMachine;

      // Check if this is credential-only mode (either from Add Credential button or Repository Credentials tab)
      const isCredentialOnlyMode =
        (existingData?.repositoryGuid &&
          typeof existingData.repositoryGuid === 'string' &&
          existingData.repositoryGuid.trim() !== '') ||
        creationContext === 'credentials-only';

      // Get machines for the team (use existingData teamName if available)
      const _teamName = existingData?.teamName || 'Private Team';
      const machinesByTeam = dropdownData?.machinesByTeam ?? [];
      const teamMachines =
        machinesByTeam.find((team) => team.teamName === _teamName)?.machines || [];

      // Only show machine selection if not prefilled and not in credential-only mode
      if (!isPrefilledMachine && !isCredentialOnlyMode) {
        simpleFields.push({
          name: 'machineName',
          label: t('machines:machine'),
          placeholder: t('machines:placeholders.selectMachine'),
          required: false,
          type: 'select' as const,
          options: teamMachines.map((machine: { value: string; label: string }) => ({
            value: machine.value,
            label: machine.label,
          })),
          helperText: t('repositories.machineHelperText', {
            defaultValue: 'Optional: Select a machine to provision storage',
          }),
        });
      }

      // Size field for repository provisioning - only show if not in credential-only mode
      if (!isCredentialOnlyMode) {
        simpleFields.push({
          name: 'size',
          label: t('repositories.size'),
          placeholder: t('repositories.placeholders.enterSize'),
          required: false,
          type: 'size' as const,
          sizeUnits: ['G', 'T'],
          helperText: t('repositories.sizeHelperText', {
            defaultValue: 'Optional: Specify size if provisioning storage (e.g., 10G, 100G, 1T)',
          }),
        });
      }

      // Show repositoryGuid field in credential-only mode
      if (isCredentialOnlyMode) {
        simpleFields.push({
          name: 'repositoryGuid',
          label: t('repositories.guid', { defaultValue: 'Repository GUID' }),
          type: 'text' as const,
          readOnly: !!(
            existingData?.repositoryGuid &&
            typeof existingData.repositoryGuid === 'string' &&
            existingData.repositoryGuid.trim() !== ''
          ), // Only read-only if GUID exists
          required: true, // Make it required in credential-only mode
          helperText: existingData?.repositoryGuid
            ? t('repositories.guidHelperText', {
                defaultValue: 'This repository already exists on the machine.',
              })
            : t('repositories.guidHelperTextNew', {
                defaultValue:
                  'Enter the repository GUID (e.g., 550e8400-e29b-41d4-a716-446655440000)',
              }),
        });
      }
    }

    return simpleFields;
  }

  const fields = [];
  if (!isTeamPreselected) fields.push(createTeamField(dropdownData, t));

  if (resourceType === 'machine') {
    fields.push(createRegionField(dropdownData, t));
    // Hide bridge field when disableBridge flag is enabled
    // Note: bridgeName value is still auto-selected and sent to backend
    if (!featureFlags.isEnabled('disableBridge')) {
      fields.push(createBridgeField(getFormValue, getFilteredBridges, t));
    }
    fields.push(nameField);
  } else if (resourceType === 'bridge') {
    fields.push(createRegionField(dropdownData, t), nameField);
  } else if (resourceType === 'repository') {
    // Repository creation needs machine selection and size
    fields.push(nameField);

    // Check if machine is prefilled
    const isPrefilledMachine = existingData?.prefilledMachine;

    // Check if this is credential-only mode (either from Add Credential button or Repository Credentials tab)
    const isCredentialOnlyMode =
      (existingData?.repositoryGuid &&
        typeof existingData.repositoryGuid === 'string' &&
        existingData.repositoryGuid.trim() !== '') ||
      creationContext === 'credentials-only';

    // Get machines for the selected team
    const selectedTeamName =
      getFormValue('teamName') ||
      existingData?.teamName ||
      (isTeamPreselected ? (Array.isArray(teamFilter) ? teamFilter[0] : teamFilter) : '');
    const machinesByTeamFull = dropdownData?.machinesByTeam ?? [];
    const teamMachines =
      machinesByTeamFull.find((team) => team.teamName === selectedTeamName)?.machines || [];

    // Only show machine selection if not prefilled and not in credential-only mode
    if (!isPrefilledMachine && !isCredentialOnlyMode) {
      fields.push({
        name: 'machineName',
        label: t('machines:machine'),
        placeholder: t('machines:placeholders.selectMachine'),
        required: true,
        type: 'select' as const,
        options: teamMachines.map((machine: { value: string; label: string }) => ({
          value: machine.value,
          label: machine.label,
        })),
        disabled: !selectedTeamName || teamMachines.length === 0,
        helperText: t('repositories.machineHelperText', {
          defaultValue: 'Select a machine to provision storage',
        }),
      });
    }

    // Only show size field if not in credential-only mode
    if (!isCredentialOnlyMode) {
      fields.push({
        name: 'size',
        label: t('repositories.size'),
        placeholder: t('repositories.placeholders.enterSize'),
        required: true,
        type: 'size' as const,
        sizeUnits: ['G', 'T'],
        helperText: t('repositories.sizeHelperText', {
          defaultValue: 'Specify size for storage provisioning (e.g., 10G, 100G, 1T)',
        }),
      });
    }

    // Repository GUID field
    if (isCredentialOnlyMode) {
      // In credential-only mode, show the GUID field
      fields.push({
        name: 'repositoryGuid',
        label: t('repositories.guid', { defaultValue: 'Repository GUID' }),
        type: 'text' as const,
        readOnly: !!(
          existingData?.repositoryGuid &&
          typeof existingData.repositoryGuid === 'string' &&
          existingData.repositoryGuid.trim() !== ''
        ), // Only read-only if GUID exists
        required: true, // Make it required in credential-only mode
        helperText: existingData?.repositoryGuid
          ? t('repositories.guidHelperText', {
              defaultValue: 'This repository already exists on the machine.',
            })
          : t('repositories.guidHelperTextNew', {
              defaultValue:
                'Enter the repository GUID (e.g., 550e8400-e29b-41d4-a716-446655440000)',
            }),
      });
    } else if (isExpertMode) {
      // In expert mode (when creating new repo), show as optional editable field
      fields.push({
        name: 'repositoryGuid',
        label: t('repositories.guid', { defaultValue: 'Repository GUID' }),
        placeholder: t('repositories.placeholders.enterGuid', {
          defaultValue:
            'Optional: Enter a specific GUID (e.g., 550e8400-e29b-41d4-a716-446655440000)',
        }),
        required: false,
        type: 'text' as const,
        helperText: t('repositories.guidHelperText', {
          defaultValue:
            'Optional: Specify a custom GUID for the repository. Leave empty to auto-generate.',
        }),
      });
    }
  } else if (resourceType === 'cluster') {
    fields.push(nameField);
  } else if (resourceType === 'pool') {
    // Get clusters for the selected team
    const teamClusters = (existingData?.clusters as ClusterOption[] | undefined) || [];

    fields.push({
      name: 'clusterName',
      label: t('ceph:pools.cluster'),
      placeholder: t('ceph:pools.selectCluster'),
      required: true,
      type: 'select' as const,
      options: teamClusters.map((cluster: ClusterOption) => ({
        value: cluster.clusterName,
        label: cluster.clusterName,
      })),
      disabled: teamClusters.length === 0,
    });
    fields.push(nameField);
  } else if (resourceType === 'image') {
    // Image needs pool selection and machine assignment
    const teamPools = (existingData?.pools as PoolOption[] | undefined) || [];
    const availableMachines =
      (existingData?.availableMachines as AvailableMachineOption[] | undefined) || [];

    fields.push({
      name: 'poolName',
      label: t('ceph:images.pool'),
      placeholder: t('ceph:images.selectPool'),
      required: true,
      type: 'select' as const,
      options: teamPools.map((pool: PoolOption) => ({
        value: pool.poolName,
        label: `${pool.poolName} (${pool.clusterName})`,
      })),
      disabled: teamPools.length === 0,
    });
    fields.push(nameField);

    // Add machine selection for image creation
    if (mode === 'create') {
      fields.push({
        name: 'machineName',
        label: t('ceph:images.machine'),
        placeholder: t('ceph:images.selectMachine'),
        required: true,
        type: 'select' as const,
        options: availableMachines.map((machine) => ({
          value: machine.machineName,
          label: machine.machineName,
          disabled: machine.status !== 'AVAILABLE',
        })),
        disabled: availableMachines.length === 0,
        helperText: availableMachines.length === 0 ? t('machines:noMachinesFound') : undefined,
      });
    }
  } else if (resourceType === 'snapshot') {
    // Snapshot needs pool and image selection
    const teamPools = (existingData?.pools as PoolOption[] | undefined) || [];
    const selectedPoolName = getFormValue('poolName') || existingData?.poolName;
    const poolImages = (existingData?.images as PoolImageOption[] | undefined) || [];

    if (!existingData?.poolName) {
      fields.push({
        name: 'poolName',
        label: t('ceph:snapshots.pool'),
        placeholder: t('ceph:snapshots.selectPool'),
        required: true,
        type: 'select' as const,
        options: teamPools.map((pool: PoolOption) => ({
          value: pool.poolName,
          label: `${pool.poolName} (${pool.clusterName})`,
        })),
        disabled: teamPools.length === 0,
      });
    }

    fields.push({
      name: 'imageName',
      label: t('ceph:snapshots.image'),
      placeholder: t('ceph:snapshots.selectImage'),
      required: true,
      type: 'select' as const,
      options: poolImages.map((image: { imageName: string }) => ({
        value: image.imageName,
        label: image.imageName,
      })),
      disabled: !selectedPoolName || poolImages.length === 0,
    });
    fields.push(nameField);
  } else if (resourceType === 'clone') {
    // Clone needs pool, image, and snapshot selection
    const teamPools = (existingData?.pools as PoolOption[] | undefined) || [];
    const selectedPoolName = getFormValue('poolName') || existingData?.poolName;
    const poolImages = (existingData?.images as PoolImageOption[] | undefined) || [];
    const selectedImageName = getFormValue('imageName') || existingData?.imageName;
    const imageSnapshots = (existingData?.snapshots as SnapshotOption[] | undefined) || [];

    if (!existingData?.poolName) {
      fields.push({
        name: 'poolName',
        label: t('ceph:clones.pool'),
        placeholder: t('ceph:clones.selectPool'),
        required: true,
        type: 'select' as const,
        options: teamPools.map((pool: PoolOption) => ({
          value: pool.poolName,
          label: `${pool.poolName} (${pool.clusterName})`,
        })),
        disabled: teamPools.length === 0,
      });
    }

    if (!existingData?.imageName) {
      fields.push({
        name: 'imageName',
        label: t('ceph:clones.image'),
        placeholder: t('ceph:clones.selectImage'),
        required: true,
        type: 'select' as const,
        options: poolImages.map((image: { imageName: string }) => ({
          value: image.imageName,
          label: image.imageName,
        })),
        disabled: !selectedPoolName || poolImages.length === 0,
      });
    }

    fields.push({
      name: 'snapshotName',
      label: t('ceph:clones.snapshot'),
      placeholder: t('ceph:clones.selectSnapshot'),
      required: true,
      type: 'select' as const,
      options: imageSnapshots.map((snapshot: { snapshotName: string }) => ({
        value: snapshot.snapshotName,
        label: snapshot.snapshotName,
      })),
      disabled: !selectedImageName || imageSnapshots.length === 0,
    });
    fields.push(nameField);
  } else if (!['team', 'region'].includes(resourceType)) {
    fields.push(nameField);
  } else {
    return [nameField];
  }

  return fields.length ? fields : [nameField];
};
