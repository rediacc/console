import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { Modal, Space, Typography, Upload, message } from 'antd';
// message.error is imported from antd
import { AppstoreOutlined } from '@/utils/optimizedIcons';
import { useForm, type Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { RootState } from '@/store/store';
import ResourceFormWithVault, {
  type FormFieldConfig,
  type ImportExportHandlers,
  type ResourceFormWithVaultRef,
} from '@/components/common/UnifiedResourceModal/components/ResourceFormWithVault';
import VaultEditorModal from '@/components/common/VaultEditorModal';
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal';
import TemplateSelector from '@/components/common/TemplateSelector';
import TemplatePreviewModal from '@/components/common/TemplatePreviewModal';
import { useDropdownData } from '@/api/queries/useDropdownData';
import type { Machine, Repo } from '@/types';
import type { Team } from '@rediacc/shared/types';
import type { QueueFunction } from '@/api/queries/queue';
import { templateService } from '@/services/templateService';
import { useDialogState } from '@/hooks/useDialogState';
import {
  createMachineSchema,
  createRepoSchema,
  createStorageSchema,
  createTeamSchema,
  createRegionSchema,
  createBridgeSchema,
  createClusterSchema,
  createPoolSchema,
  createImageSchema,
  createSnapshotSchema,
  createCloneSchema,
} from '@/utils/validation';
import { z } from 'zod';
import { ModalSize } from '@/types/modal';
import { featureFlags } from '@/config/featureFlags';
import {
  TitleStack,
  TitleText,
  SubtitleText,
  SecondaryLabel,
  FooterLeftActions,
  ActionButton,
  PrimaryActionButton,
  AutoSetupCheckbox,
  UploadIcon,
  DownloadIcon,
  TemplateCollapse,
  SelectedTemplateTag,
} from './styles';

const { Text } = Typography;

export type ResourceType =
  | 'machine'
  | 'repo'
  | 'storage'
  | 'team'
  | 'region'
  | 'bridge'
  | 'cluster'
  | 'pool'
  | 'image'
  | 'snapshot'
  | 'clone';

export interface UnifiedResourceModalProps {
  open: boolean;
  onCancel: () => void;
  resourceType: ResourceType;
  mode: 'create' | 'edit' | 'vault';
  existingData?: ExistingResourceData;
  teamFilter?: string | string[];
  onSubmit: (data: ResourceFormValues) => Promise<void>;
  onUpdateVault?: (vault: string, version: number) => Promise<void>;
  onFunctionSubmit?: (functionData: FunctionSubmitPayload) => Promise<void>;
  isSubmitting?: boolean;
  isUpdatingVault?: boolean;
  functionCategories?: string[];
  hiddenParams?: string[];
  defaultParams?: FunctionParamsMap;
  preselectedFunction?: string;
  creationContext?: 'credentials-only' | 'normal';
}

type ResourceFormValues = Record<string, unknown>;

type ExistingResourceData = Partial<Machine> &
  Partial<Repo> &
  Partial<Team> & {
    prefilledMachine?: boolean;
    clusters?: ClusterOption[];
    pools?: PoolOption[];
    availableMachines?: AvailableMachineOption[];
    images?: Array<{ imageName: string }>;
    snapshots?: Array<{ snapshotName: string }>;
  } & Record<string, unknown>;

type FunctionParamsMap = Record<string, string | number | string[] | undefined>;

type FunctionSubmitPayload = {
  function: QueueFunction;
  params: FunctionParamsMap;
  priority: number;
  description: string;
  selectedMachine?: string;
};

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

const UnifiedResourceModal: React.FC<UnifiedResourceModalProps> = ({
  open,
  onCancel,
  resourceType,
  mode,
  existingData,
  teamFilter,
  onSubmit,
  onUpdateVault,
  onFunctionSubmit,
  isSubmitting = false,
  isUpdatingVault = false,
  functionCategories = [],
  hiddenParams = [],
  defaultParams = {},
  preselectedFunction,
  creationContext,
}) => {
  const { t } = useTranslation(['resources', 'machines', 'common', 'distributedStorage', 'system']);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const isExpertMode = uiMode === 'expert';
  const { data: dropdownData } = useDropdownData();
  const formRef = useRef<ResourceFormWithVaultRef | null>(null);

  // State for sub-modals
  const vaultModal = useDialogState<void>();
  const functionModal = useDialogState<void>();
  const { isOpen: isFunctionModalOpen, open: openFunctionModal } = functionModal;

  // State for test connection (for machines)
  const [testConnectionSuccess, setTestConnectionSuccess] = useState(false);

  // Track test connection state changes
  useEffect(() => {
    // Test connection state updated
  }, [testConnectionSuccess, resourceType, mode]);

  // State for auto-setup after machine creation
  const [autoSetupEnabled, setAutoSetupEnabled] = useState(true);

  const resolvePreselectedTemplate = (): string | null => {
    if (
      existingData &&
      typeof (existingData as Record<string, unknown>).preselectedTemplate === 'string'
    ) {
      return (existingData as Record<string, string>).preselectedTemplate || null;
    }
    return null;
  };

  // State for template selection (for repos)
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(
    resolvePreselectedTemplate()
  );
  const [showTemplateDetails, setShowTemplateDetails] = useState(false);
  const [templateToView, setTemplateToView] = useState<string | null>(null);

  // Import/Export handlers ref
  const importExportHandlers = useRef<ImportExportHandlers | null>(null);

  // Resource configuration
  const RESOURCE_CONFIG = {
    storage: { key: 'storage', createKey: 'resources:storage.createStorage' },
    repo: { key: 'repos', createKey: 'resources:repos.createRepo' },
    machine: { key: 'machines', createKey: 'machines:createMachine' },
    team: { key: 'teams', createKey: 'resources:teams.createTeam' },
    region: { key: 'regions', createKey: 'system:regions.createRegion' },
    bridge: { key: 'bridges', createKey: 'system:bridges.createBridge' },
    cluster: { key: 'clusters', createKey: 'distributedStorage:clusters.createCluster' },
    pool: { key: 'pools', createKey: 'distributedStorage:pools.createPool' },
    image: { key: 'images', createKey: 'distributedStorage:images.createImage' },
    snapshot: { key: 'snapshots', createKey: 'distributedStorage:snapshots.createSnapshot' },
    clone: { key: 'clones', createKey: 'distributedStorage:clones.createClone' },
  } as const;

  // Helper functions
  const getResourceTranslationKey = () =>
    RESOURCE_CONFIG[resourceType as keyof typeof RESOURCE_CONFIG]?.key || `${resourceType}s`;
  const mapToOptions = (items?: Array<{ value: string; label: string }>) =>
    items?.map((item) => ({ value: item.value, label: item.label })) || [];

  // Log when modal opens
  useEffect(() => {
    if (open) {
      // Modal opened with resource configuration
    }
  }, [open, resourceType, mode, uiMode, existingData, teamFilter]);

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
              machineVault: z.string().optional().default('{}'),
            })
          : createMachineSchema,
      repo: createRepoSchema,
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

    // For repo creation in credentials-only mode, use simpler validation
    if (resourceType === 'repo' && creationContext === 'credentials-only') {
      return z.object({
        teamName: z.string().min(1, 'Team name is required'),
        repoName: z.string().min(1, 'Repo name is required'),
        repoGuid: z.string().min(1, 'Repo GUID is required'),
        repoVault: z.string().optional().default('{}'),
      });
    }

    return schemaMap[resourceType as keyof typeof schemaMap] || z.object({});
  }, [creationContext, mode, resourceType, schemaMap]);

  // Default values factory
  const getDefaultValues = (): ResourceFormValues => {
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
        [`${resourceType}Vault`]: existingData.vaultContent || '{}',
      };
    }

    const baseDefaults: ResourceFormValues = {
      teamName: uiMode === 'simple' ? 'Private Team' : '',
      [`${resourceType}Vault`]: '{}',
      [`${resourceType}Name`]: '',
    };

    const resourceDefaults = {
      machine: {
        regionName: uiMode === 'simple' ? 'Default Region' : '',
        bridgeName: uiMode === 'simple' ? 'Global Bridges' : '',
        machineVault: '{}',
      },
      repo: {
        machineName: '',
        size: '',
        repoGuid: '', // Add default for repoGuid
      },
      team: { teamName: '', teamVault: '{}' },
      region: { regionName: '', regionVault: '{}' },
      bridge: { regionName: '', bridgeName: '', bridgeVault: '{}' },
      cluster: { clusterName: '', clusterVault: '{}' },
      pool: { clusterName: '', poolName: '', poolVault: '{}' },
      image: { poolName: '', imageName: '', imageVault: '{}' },
      snapshot: { poolName: '', imageName: '', snapshotName: '', snapshotVault: '{}' },
      clone: { poolName: '', imageName: '', snapshotName: '', cloneName: '', cloneVault: '{}' },
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
  };

  const schema = useMemo(() => getSchema(), [getSchema]);

  const form = useForm<ResourceFormValues>({
    resolver: zodResolver(schema) as unknown as Resolver<
      ResourceFormValues,
      Record<string, unknown>,
      ResourceFormValues
    >,
    defaultValues: getDefaultValues(),
  });

  const getFormValue = useCallback(
    (field: string): string | undefined => {
      const rawValue = form.getValues(field as keyof ResourceFormValues);
      return typeof rawValue === 'string' ? rawValue : undefined;
    },
    [form]
  );

  // Get filtered bridges based on selected region - moved inside getFormFields to avoid unnecessary re-renders
  const getFilteredBridges = useCallback(
    (regionName: string | null): Array<{ value: string; label: string }> => {
      if (!regionName || !dropdownData?.bridgesByRegion) return [];

      const bridgesByRegion = dropdownData.bridgesByRegion ?? [];
      const regionData = bridgesByRegion.find((region) => region.regionName === regionName);
      const bridges = regionData?.bridges ?? [];
      return bridges.map((bridge) => ({
        value: bridge.value,
        label: bridge.label,
      }));
    },
    [dropdownData?.bridgesByRegion]
  );

  // Clear bridge selection when region changes, or auto-select if bridge disabled
  useEffect(() => {
    if (resourceType === 'machine') {
      const subscription = form.watch((value, { name }) => {
        if (name === 'regionName') {
          const regionValue = typeof value.regionName === 'string' ? value.regionName : null;
          if (!regionValue) {
            return;
          }
          const currentBridge = getFormValue('bridgeName');
          const filteredBridges = getFilteredBridges(regionValue);

          // If bridge feature is disabled, auto-select first available bridge
          if (featureFlags.isEnabled('disableBridge')) {
            if (filteredBridges.length > 0) {
              form.setValue('bridgeName', filteredBridges[0].value);
            }
          } else {
            // Normal behavior: clear bridge if it's not valid for the new region
            if (currentBridge && !filteredBridges.find((b) => b.value === currentBridge)) {
              form.setValue('bridgeName', '');
            }
          }
        }
      });
      return () => subscription.unsubscribe();
    }
  }, [form, resourceType, getFilteredBridges, getFormValue]);

  // Set default values when modal opens
  useEffect(() => {
    if (open && mode === 'create') {
      // Reset form to default values first
      form.reset(getDefaultValues());

      // Reset template selection for repos (unless preselected)
      if (resourceType === 'repo') {
        const preselected = resolvePreselectedTemplate();
        setSelectedTemplate(preselected);
      }

      // Set team if preselected or from existing data
      if (existingData?.teamName) {
        form.setValue('teamName', existingData.teamName);
      } else if (teamFilter) {
        if (Array.isArray(teamFilter) && teamFilter.length === 1) {
          const [singleTeam] = teamFilter;
          if (singleTeam) {
            form.setValue('teamName', singleTeam);
          }
        } else if (!Array.isArray(teamFilter)) {
          form.setValue('teamName', teamFilter);
        }
      }

      // For repos, set prefilled machine
      if (resourceType === 'repo' && existingData?.machineName) {
        form.setValue('machineName', existingData.machineName);
      }

      // For machines, set default region and bridge
      // NOTE: Even when disableBridge is enabled and bridge field is hidden,
      // we still auto-select the first bridge to satisfy backend requirements
      if (resourceType === 'machine' && dropdownData?.regions && dropdownData.regions.length > 0) {
        const firstRegion = dropdownData.regions[0].value;
        form.setValue('regionName', firstRegion);

        const regionBridges = dropdownData.bridgesByRegion?.find(
          (region) => region.regionName === firstRegion
        );

        if (regionBridges?.bridges && regionBridges.bridges.length > 0) {
          const firstBridge = regionBridges.bridges[0].value;
          form.setValue('bridgeName', firstBridge);
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mode, teamFilter, resourceType, form, dropdownData, existingData]);

  // Reset form values when modal opens in edit mode
  useEffect(() => {
    if (open && mode === 'edit' && existingData) {
      form.reset({
        [`${resourceType}Name`]: existingData[`${resourceType}Name`],
        ...(resourceType === 'machine' && {
          regionName: existingData.regionName,
          // NOTE: bridgeName is preserved even when disableBridge is enabled and field is hidden
          bridgeName: existingData.bridgeName,
        }),
        ...(resourceType === 'bridge' && {
          regionName: existingData.regionName,
        }),
        ...(resourceType === 'pool' && {
          clusterName: existingData.clusterName,
        }),
        ...(resourceType === 'image' && {
          poolName: existingData.poolName,
        }),
        ...(resourceType === 'snapshot' && {
          poolName: existingData.poolName,
          imageName: existingData.imageName,
        }),
        ...(resourceType === 'clone' && {
          poolName: existingData.poolName,
          imageName: existingData.imageName,
          snapshotName: existingData.snapshotName,
        }),
        [`${resourceType}Vault`]: existingData.vaultContent || '{}',
      });
    }
  }, [open, mode, existingData, resourceType, form]);

  // Determine if team is already selected/known
  const isTeamPreselected =
    uiMode === 'simple' ||
    (teamFilter && !Array.isArray(teamFilter)) ||
    (teamFilter && Array.isArray(teamFilter) && teamFilter.length === 1);

  // Field factories
  const createNameField = (): FormFieldConfig => ({
    name: `${resourceType}Name`,
    label: t(`${getResourceTranslationKey()}.${resourceType}Name`),
    placeholder: t(
      `${getResourceTranslationKey()}.placeholders.enter${resourceType.charAt(0).toUpperCase() + resourceType.slice(1)}Name`
    ),
    required: true,
  });

  const createTeamField = (): FormFieldConfig => ({
    name: 'teamName',
    label: t('general.team'),
    placeholder: t('teams.placeholders.selectTeam'),
    required: true,
    type: 'select' as const,
    options: mapToOptions(dropdownData?.teams),
  });

  const createRegionField = (): FormFieldConfig => ({
    name: 'regionName',
    label: t('general.region'),
    placeholder: t('regions.placeholders.selectRegion'),
    required: true,
    type: 'select' as const,
    options: mapToOptions(dropdownData?.regions) as Array<{ value: string; label: string }>,
  });

  const createBridgeField = (): FormFieldConfig => {
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

  // Get form fields based on resource type and mode
  const getFormFields = (): FormFieldConfig[] => {
    const nameField = createNameField();

    if (mode === 'edit') {
      if (resourceType === 'machine') {
        const fields = [nameField, createRegionField()];
        // Hide bridge field when disableBridge flag is enabled
        // Note: existing bridgeName value is preserved and sent to backend
        if (!featureFlags.isEnabled('disableBridge')) {
          fields.push(createBridgeField());
        }
        return fields;
      }
      if (resourceType === 'bridge') return [nameField, createRegionField()];
      // For repos in edit mode, we still need to show the vault fields
      // so users can update credentials if needed
      if (resourceType === 'repo') {
        // Don't include team field in edit mode since team can't be changed
        return [nameField];
      }
      return [nameField];
    }

    if (uiMode === 'simple') {
      const simpleFields = [nameField];

      // For repo creation, we need to include size field and potentially machine selection
      if (resourceType === 'repo') {
        // Check if machine is prefilled
        const isPrefilledMachine = existingData?.prefilledMachine;

        // Check if this is credential-only mode (either from Add Credential button or Repo Credentials tab)
        const isCredentialOnlyMode =
          (existingData?.repoGuid && existingData?.repoGuid.trim() !== '') ||
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
            helperText: t('repos.machineHelperText', {
              defaultValue: 'Optional: Select a machine to provision storage',
            }),
          });
        }

        // Size field for repo provisioning - only show if not in credential-only mode
        if (!isCredentialOnlyMode) {
          simpleFields.push({
            name: 'size',
            label: t('repos.size'),
            placeholder: t('repos.placeholders.enterSize'),
            required: false,
            type: 'size' as const,
            sizeUnits: ['G', 'T'],
            helperText: t('repos.sizeHelperText', {
              defaultValue: 'Optional: Specify size if provisioning storage (e.g., 10G, 100G, 1T)',
            }),
          });
        }

        // Show repoGuid field in credential-only mode
        if (isCredentialOnlyMode) {
          simpleFields.push({
            name: 'repoGuid',
            label: t('repos.guid', { defaultValue: 'Repo GUID' }),
            type: 'text' as const,
            readOnly: !!(existingData?.repoGuid && existingData.repoGuid.trim() !== ''), // Only read-only if GUID exists
            required: true, // Make it required in credential-only mode
            helperText: existingData?.repoGuid
              ? t('repos.guidHelperText', {
                  defaultValue: 'This repo already exists on the machine.',
                })
              : t('repos.guidHelperTextNew', {
                  defaultValue: 'Enter the repo GUID (e.g., 550e8400-e29b-41d4-a716-446655440000)',
                }),
          });
        }
      }

      return simpleFields;
    }

    const fields = [];
    if (!isTeamPreselected) fields.push(createTeamField());

    if (resourceType === 'machine') {
      fields.push(createRegionField());
      // Hide bridge field when disableBridge flag is enabled
      // Note: bridgeName value is still auto-selected and sent to backend
      if (!featureFlags.isEnabled('disableBridge')) {
        fields.push(createBridgeField());
      }
      fields.push(nameField);
    } else if (resourceType === 'bridge') {
      fields.push(createRegionField(), nameField);
    } else if (resourceType === 'repo') {
      // Repo creation needs machine selection and size
      fields.push(nameField);

      // Check if machine is prefilled
      const isPrefilledMachine = existingData?.prefilledMachine;

      // Check if this is credential-only mode (either from Add Credential button or Repo Credentials tab)
      const isCredentialOnlyMode =
        (existingData?.repoGuid && existingData?.repoGuid.trim() !== '') ||
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
          helperText: t('repos.machineHelperText', {
            defaultValue: 'Select a machine to provision storage',
          }),
        });
      }

      // Only show size field if not in credential-only mode
      if (!isCredentialOnlyMode) {
        fields.push({
          name: 'size',
          label: t('repos.size'),
          placeholder: t('repos.placeholders.enterSize'),
          required: true,
          type: 'size' as const,
          sizeUnits: ['G', 'T'],
          helperText: t('repos.sizeHelperText', {
            defaultValue: 'Specify size for storage provisioning (e.g., 10G, 100G, 1T)',
          }),
        });
      }

      // Repo GUID field
      if (isCredentialOnlyMode) {
        // In credential-only mode, show the GUID field
        fields.push({
          name: 'repoGuid',
          label: t('repos.guid', { defaultValue: 'Repo GUID' }),
          type: 'text' as const,
          readOnly: !!(existingData?.repoGuid && existingData.repoGuid.trim() !== ''), // Only read-only if GUID exists
          required: true, // Make it required in credential-only mode
          helperText: existingData?.repoGuid
            ? t('repos.guidHelperText', {
                defaultValue: 'This repo already exists on the machine.',
              })
            : t('repos.guidHelperTextNew', {
                defaultValue: 'Enter the repo GUID (e.g., 550e8400-e29b-41d4-a716-446655440000)',
              }),
        });
      } else if (isExpertMode) {
        // In expert mode (when creating new repo), show as optional editable field
        fields.push({
          name: 'repoGuid',
          label: t('repos.guid', { defaultValue: 'Repo GUID' }),
          placeholder: t('repos.placeholders.enterGuid', {
            defaultValue:
              'Optional: Enter a specific GUID (e.g., 550e8400-e29b-41d4-a716-446655440000)',
          }),
          required: false,
          type: 'text' as const,
          helperText: t('repos.guidHelperText', {
            defaultValue:
              'Optional: Specify a custom GUID for the repo. Leave empty to auto-generate.',
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
        label: t('distributedStorage:pools.cluster'),
        placeholder: t('distributedStorage:pools.selectCluster'),
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
        label: t('distributedStorage:images.pool'),
        placeholder: t('distributedStorage:images.selectPool'),
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
          label: t('distributedStorage:images.machine'),
          placeholder: t('distributedStorage:images.selectMachine'),
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
          label: t('distributedStorage:snapshots.pool'),
          placeholder: t('distributedStorage:snapshots.selectPool'),
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
        label: t('distributedStorage:snapshots.image'),
        placeholder: t('distributedStorage:snapshots.selectImage'),
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
          label: t('distributedStorage:clones.pool'),
          placeholder: t('distributedStorage:clones.selectPool'),
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
          label: t('distributedStorage:clones.image'),
          placeholder: t('distributedStorage:clones.selectImage'),
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
        label: t('distributedStorage:clones.snapshot'),
        placeholder: t('distributedStorage:clones.selectSnapshot'),
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

  // Helper functions
  const getEntityType = () => resourceType.toUpperCase();
  const getVaultFieldName = () => `${resourceType}Vault`;

  const createFunctionSubtitle = (): React.ReactNode => {
    if (!existingData) {
      return null;
    }

    const teamLabel: string =
      typeof existingData.teamName === 'string' ? existingData.teamName : t('common:unknown');

    const resourceNameKey = `${resourceType}Name`;
    const resourceNameValue = (existingData as Record<string, unknown>)[resourceNameKey];
    const resourceName: string = typeof resourceNameValue === 'string' ? resourceNameValue : '';

    return (
      <Space size="small">
        <Text type="secondary">{t('machines:team')}:</Text>
        <Text strong>{teamLabel}</Text>
        {['machine', 'repo', 'storage'].includes(resourceType) && resourceName && (
          <>
            <SecondaryLabel type="secondary">
              {t(
                resourceType === 'machine'
                  ? 'machines:machine'
                  : resourceType === 'storage'
                    ? 'resources:storage.storage'
                    : 'repos.repo'
              )}
              :
            </SecondaryLabel>
            <Text strong>{resourceName}</Text>
          </>
        )}
      </Space>
    );
  };

  const getFunctionTitle = () => {
    if (resourceType === 'machine') return t('machines:systemFunctions');
    if (resourceType === 'storage') return t('resources:storage.storageFunctions');
    return t(`${getResourceTranslationKey()}.${resourceType}Functions`);
  };

  // Get modal title
  const getModalTitle = () => {
    if (mode === 'create') {
      const createKey = RESOURCE_CONFIG[resourceType as keyof typeof RESOURCE_CONFIG]?.createKey;
      const createText = createKey ? t(createKey) : '';

      // Special case for repo creation
      if (resourceType === 'repo') {
        // Check if this is credential-only mode (either from Add Credential button or Repo Credentials tab)
        const isCredentialOnlyMode =
          (existingData?.repoGuid && existingData?.repoGuid.trim() !== '') ||
          creationContext === 'credentials-only';

        if (isCredentialOnlyMode) {
          // For credential-only mode, show "Create Repo (Credentials) in [team]"
          const team =
            existingData?.teamName ||
            (uiMode === 'simple'
              ? 'Private Team'
              : Array.isArray(teamFilter)
                ? teamFilter[0]
                : teamFilter);
          return `Create Repo (Credentials) in ${team}`;
        } else if (existingData?.machineName) {
          // For repo creation from machine
          return `${createText} for ${existingData.machineName}`;
        }
      }

      if (resourceType === 'machine') {
        return createText;
      }

      if (isTeamPreselected) {
        const team =
          uiMode === 'expert' && teamFilter
            ? Array.isArray(teamFilter)
              ? teamFilter[0]
              : teamFilter
            : 'Private Team';
        return `${createText} in ${team}`;
      }
      return createText;
    }
    return `${t('resources:general.edit')} ${t(`resources:${getResourceTranslationKey()}.${resourceType}Name`)}`;
  };

  const getModalSubtitle = () => {
    if (!(mode === 'create' && resourceType === 'machine')) return '';

    const formTeam = getFormValue('teamName');
    if (formTeam) return formTeam;

    if (existingData?.teamName) return existingData.teamName;

    // Simple mode always shows "Private Team"
    if (!isExpertMode) return 'Private Team';

    // Expert mode: show team filter if available
    if (teamFilter) {
      return Array.isArray(teamFilter) ? teamFilter[0] : teamFilter;
    }

    return isExpertMode ? '' : 'Private Team';
  };

  const resolveTeamName = () => {
    const formTeam = getFormValue('teamName');
    if (formTeam) return formTeam;
    if (existingData?.teamName) return existingData.teamName;
    if (teamFilter) {
      const filterValue = Array.isArray(teamFilter) ? teamFilter[0] : teamFilter;
      if (typeof filterValue === 'string' && filterValue) {
        return filterValue;
      }
    }
    return 'Private Team';
  };

  const resolveBridgeName = () => {
    const formBridge = getFormValue('bridgeName');
    if (formBridge) return formBridge;
    return 'Global Bridges';
  };

  const renderModalTitle = () => {
    const baseTitle = getModalTitle();

    if (mode === 'create' && resourceType === 'machine') {
      const subtitle = getModalSubtitle();
      return (
        <TitleStack>
          <TitleText>{baseTitle}</TitleText>
          {subtitle && (
            <SubtitleText type="secondary">
              {t('general.team')}: {subtitle}
            </SubtitleText>
          )}
        </TitleStack>
      );
    }

    return baseTitle;
  };

  // Handle form submission
  const handleSubmit = async (data: ResourceFormValues) => {
    // Validate machine creation - check if SSH password is present without SSH key configured
    if (mode === 'create' && resourceType === 'machine') {
      const vaultString = typeof data.machineVault === 'string' ? data.machineVault : '';
      const vaultData: Record<string, unknown> = vaultString ? JSON.parse(vaultString) : {};
      const sshPassword = vaultData.ssh_password;
      const sshKeyConfigured = vaultData.ssh_key_configured;
      // Only block if password exists AND SSH key is not configured
      if (typeof sshPassword === 'string' && sshPassword && !sshKeyConfigured) {
        message.error(t('machines:validation.sshPasswordNotAllowed'));
        return;
      }

      if (!testConnectionSuccess) {
        message.warning(
          t('machines:validation.sshConnectionNotTested', {
            defaultValue:
              'SSH connection has not been tested yet. We recommend running Test Connection before creating.',
          })
        );
      }
    }

    if (uiMode === 'simple' && mode === 'create') {
      // Only set defaults if not already provided
      const defaults: ResourceFormValues = {};

      // Preserve teamName from existingData if available (e.g., when creating repo from machine)
      if (!data.teamName) {
        if (existingData?.teamName) {
          defaults.teamName = existingData.teamName;
        } else {
          defaults.teamName = 'Private Team';
        }
      }

      // Set machine-specific defaults
      if (resourceType === 'machine') {
        defaults.regionName = 'Default Region';
        defaults.bridgeName = 'Global Bridges';
      }

      Object.assign(data, defaults);
    }

    // For repo creation from machine, ensure machine name is included
    if (resourceType === 'repo' && existingData?.machineName && existingData?.prefilledMachine) {
      data.machineName = existingData.machineName;
      // Also ensure teamName is preserved
      if (existingData?.teamName && !data.teamName) {
        data.teamName = existingData.teamName;
      }
    }

    // Add template parameter for repo creation
    if (resourceType === 'repo' && mode === 'create' && selectedTemplate) {
      try {
        // Fetch the template details by ID using templateService
        data.tmpl = await templateService.getEncodedTemplateDataById(selectedTemplate);
      } catch (error) {
        console.error('Failed to load template:', error);
        message.warning(t('resources:templates.failedToLoadTemplate'));
      }
    }

    // Always keep repo open after creation
    if (resourceType === 'repo' && mode === 'create') {
      data.keep_open = true;
    }

    // Add auto-setup flag for machine creation
    if (mode === 'create' && resourceType === 'machine') {
      data.autoSetup = autoSetupEnabled;
    }

    // For credential-only repo creation, ensure repoGuid is included
    if (mode === 'create' && resourceType === 'repo' && existingData?.repoGuid) {
      data.repoGuid = existingData.repoGuid;
    }

    await onSubmit(data);
  };

  // Show functions button only for machines, repos, and storage
  const showFunctions =
    (resourceType === 'machine' || resourceType === 'repo' || resourceType === 'storage') &&
    mode === 'create' &&
    existingData &&
    !existingData.prefilledMachine && // Don't show functions when creating repo from machine
    onFunctionSubmit &&
    functionCategories.length > 0;

  // Auto-open function modal if we're in create mode with existing data (for repo functions)
  // WARNING: The !functionModal.isOpen check is critical to prevent infinite render loops!
  // Without it, each call to functionModal.open() triggers a state change, causing re-render,
  // which triggers this effect again, leading to "Maximum update depth exceeded" error.
  useEffect(() => {
    if (open && mode === 'create' && existingData && showFunctions && !isFunctionModalOpen) {
      openFunctionModal();
    }
  }, [open, mode, existingData, showFunctions, isFunctionModalOpen, openFunctionModal]);

  // If we're in vault mode, show the vault editor directly
  if (mode === 'vault' && existingData && onUpdateVault) {
    return (
      <VaultEditorModal
        open={open}
        onCancel={onCancel}
        onSave={async (vault, version) => {
          await onUpdateVault(vault, version);
          onCancel();
        }}
        entityType={getEntityType()}
        title={t('general.configureVault', { name: existingData[`${resourceType}Name`] || '' })}
        initialVault={existingData.vaultContent || '{}'}
        initialVersion={existingData.vaultVersion || 1}
        loading={isUpdatingVault}
      />
    );
  }

  // If we're showing functions directly, don't show the main modal
  if (
    mode === 'create' &&
    existingData &&
    showFunctions &&
    functionModal.isOpen &&
    !existingData.prefilledMachine
  ) {
    return (
      <>
        {/* Function Selection Modal */}
        <FunctionSelectionModal
          open={functionModal.isOpen}
          onCancel={() => {
            functionModal.close();
            onCancel();
          }}
          onSubmit={async (functionData) => {
            await onFunctionSubmit(functionData);
            functionModal.close();
            onCancel();
          }}
          title={getFunctionTitle()}
          subtitle={createFunctionSubtitle()}
          allowedCategories={functionCategories}
          loading={isSubmitting}
          showMachineSelection={resourceType === 'repo' || resourceType === 'storage'}
          teamName={existingData?.teamName}
          machines={
            dropdownData?.machinesByTeam?.find((t) => t.teamName === existingData?.teamName)
              ?.machines || []
          }
          hiddenParams={hiddenParams}
          defaultParams={defaultParams}
          preselectedFunction={preselectedFunction}
        />
      </>
    );
  }

  return (
    <>
      <Modal
        data-testid="resource-modal"
        title={renderModalTitle()}
        open={open}
        onCancel={onCancel}
        destroyOnHidden
        footer={[
          ...(mode === 'create' && uiMode === 'expert'
            ? [
                <FooterLeftActions key="left-buttons">
                  <Space>
                    <Upload
                      data-testid="resource-modal-upload-json"
                      accept=".json"
                      showUploadList={false}
                      beforeUpload={(file) => {
                        if (importExportHandlers.current) {
                          return importExportHandlers.current.handleImport(file);
                        }
                        return false;
                      }}
                    >
                      <ActionButton
                        data-testid="resource-modal-import-button"
                        icon={<UploadIcon />}
                      >
                        {t('common:vaultEditor.importJson')}
                      </ActionButton>
                    </Upload>
                    <ActionButton
                      data-testid="resource-modal-export-button"
                      icon={<DownloadIcon />}
                      onClick={() => {
                        if (importExportHandlers.current) {
                          importExportHandlers.current.handleExport();
                        }
                      }}
                    >
                      {t('common:vaultEditor.exportJson')}
                    </ActionButton>
                  </Space>
                </FooterLeftActions>,
              ]
            : []),
          ...(mode === 'create' && resourceType === 'machine'
            ? [
                <AutoSetupCheckbox
                  key="auto-setup"
                  data-testid="resource-modal-auto-setup-checkbox"
                  checked={autoSetupEnabled}
                  onChange={(e) => setAutoSetupEnabled(e.target.checked)}
                >
                  {t('machines:autoSetupAfterCreation')}
                </AutoSetupCheckbox>,
              ]
            : []),
          <ActionButton key="cancel" data-testid="resource-modal-cancel-button" onClick={onCancel}>
            {t('general.cancel')}
          </ActionButton>,
          ...(mode === 'create' && existingData && onUpdateVault
            ? [
                <ActionButton
                  key="vault"
                  data-testid="resource-modal-vault-button"
                  onClick={() => vaultModal.open()}
                >
                  {t('general.vault')}
                </ActionButton>,
              ]
            : []),
          ...(showFunctions
            ? [
                <ActionButton
                  key="functions"
                  data-testid="resource-modal-functions-button"
                  onClick={() => functionModal.open()}
                >
                  {t(`${resourceType}s.${resourceType}Functions`)}
                </ActionButton>,
              ]
            : []),
          <PrimaryActionButton
            key="submit"
            data-testid="resource-modal-ok-button"
            type="primary"
            loading={isSubmitting}
            disabled={mode === 'create' && resourceType === 'machine' && !testConnectionSuccess}
            onClick={() => {
              if (formRef.current) {
                formRef.current.submit();
              }
            }}
          >
            {mode === 'create' ? t('general.create') : t('general.save')}
          </PrimaryActionButton>,
        ]}
        className={ModalSize.Fullscreen}
      >
        <ResourceFormWithVault
          ref={formRef}
          form={form}
          fields={getFormFields()}
          onSubmit={handleSubmit}
          entityType={getEntityType()}
          vaultFieldName={getVaultFieldName()}
          showDefaultsAlert={false}
          creationContext={creationContext}
          uiMode={uiMode}
          initialVaultData={(() => {
            if (existingData?.vaultContent) {
              try {
                let parsed = JSON.parse(existingData.vaultContent);
                // Special handling for repos - map the vault data correctly
                if (resourceType === 'repo') {
                  // The vault data might have the credential at root level or nested
                  // We need to ensure it's in the format VaultEditor expects
                  if (!parsed.credential && parsed.repoVault) {
                    // If repoVault exists, it might contain the credential
                    try {
                      const innerVault =
                        typeof parsed.repoVault === 'string'
                          ? JSON.parse(parsed.repoVault)
                          : parsed.repoVault;
                      if (innerVault.credential) {
                        parsed = { credential: innerVault.credential };
                      }
                    } catch (e) {
                      console.error('[UnifiedResourceModal] Failed to parse inner vault:', e);
                    }
                  } else if (parsed.repoVault) {
                    // Or it might be in repoVault
                    try {
                      const innerVault =
                        typeof parsed.repoVault === 'string'
                          ? JSON.parse(parsed.repoVault)
                          : parsed.repoVault;
                      if (innerVault.credential) {
                        parsed = { credential: innerVault.credential };
                      }
                    } catch (e) {
                      console.error('[UnifiedResourceModal] Failed to parse repo vault:', e);
                    }
                  }
                  // If still no credential field but we have other fields, check if any could be the credential
                  if (!parsed.credential) {
                    // Check for any 32-character string that might be the credential
                    for (const [, value] of Object.entries(parsed)) {
                      if (
                        typeof value === 'string' &&
                        value.length === 32 &&
                        /^[A-Za-z0-9!@#$%^&*()_+{}|:<>,.?/]+$/.test(value)
                      ) {
                        parsed = { credential: value };
                        break;
                      }
                    }
                  }
                }
                return parsed;
              } catch (e) {
                console.error('[UnifiedResourceModal] Failed to parse vault content:', e);
                return {};
              }
            }
            return {};
          })()}
          hideImportExport={true}
          isEditMode={mode === 'edit'}
          onImportExportRef={(handlers) => {
            importExportHandlers.current = handlers;
          }}
          teamName={resolveTeamName()}
          bridgeName={resolveBridgeName()}
          onTestConnectionStateChange={setTestConnectionSuccess}
          isModalOpen={open}
          beforeVaultContent={undefined}
          afterVaultContent={
            resourceType === 'repo' &&
            mode === 'create' &&
            creationContext !== 'credentials-only' ? (
              <TemplateCollapse
                data-testid="resource-modal-template-collapse"
                items={[
                  {
                    key: 'template',
                    label: (
                      <Space size="small">
                        <AppstoreOutlined />
                        <Text>{t('resources:templates.selectTemplate')}</Text>
                        {selectedTemplate && (
                          <SelectedTemplateTag color="blue">
                            {selectedTemplate.replace(/^(db_|kick_|route_)/, '')}
                          </SelectedTemplateTag>
                        )}
                      </Space>
                    ),
                    children: (
                      <TemplateSelector
                        value={selectedTemplate}
                        onChange={(templateId) => {
                          if (Array.isArray(templateId)) {
                            setSelectedTemplate(templateId[0] || null);
                          } else {
                            setSelectedTemplate(templateId);
                          }
                        }}
                        onViewDetails={(templateName) => {
                          setTemplateToView(templateName);
                          setShowTemplateDetails(true);
                        }}
                      />
                    ),
                  },
                ]}
              />
            ) : undefined
          }
          defaultsContent={
            <Space orientation="vertical" size={0}>
              <Text>{t('general.team')}: Private Team</Text>
              {resourceType === 'machine' && (
                <>
                  <Text>{t('machines:region')}: Default Region</Text>
                  <Text>{t('machines:bridge')}: Global Bridges</Text>
                </>
              )}
            </Space>
          }
        />
      </Modal>

      {/* Vault Editor Modal */}
      {existingData && onUpdateVault && (
        <VaultEditorModal
          open={vaultModal.isOpen}
          onCancel={vaultModal.close}
          onSave={async (vault, version) => {
            await onUpdateVault(vault, version);
            vaultModal.close();
          }}
          entityType={getEntityType()}
          title={t('general.configureVault', { name: existingData[`${resourceType}Name`] || '' })}
          initialVault={existingData.vaultContent || '{}'}
          initialVersion={existingData.vaultVersion || 1}
          loading={isUpdatingVault}
        />
      )}

      {/* Function Selection Modal */}
      {showFunctions && existingData && (
        <FunctionSelectionModal
          open={functionModal.isOpen}
          onCancel={functionModal.close}
          onSubmit={async (functionData) => {
            await onFunctionSubmit(functionData);
            functionModal.close();
          }}
          title={getFunctionTitle()}
          subtitle={createFunctionSubtitle()}
          allowedCategories={functionCategories}
          loading={isSubmitting}
          showMachineSelection={resourceType === 'repo' || resourceType === 'storage'}
          teamName={existingData?.teamName}
          machines={
            dropdownData?.machinesByTeam?.find((t) => t.teamName === existingData?.teamName)
              ?.machines || []
          }
          hiddenParams={hiddenParams}
          defaultParams={defaultParams}
          preselectedFunction={preselectedFunction}
        />
      )}

      {/* Template Preview Modal */}
      <TemplatePreviewModal
        open={showTemplateDetails}
        template={null}
        templateName={templateToView}
        onClose={() => {
          setShowTemplateDetails(false);
          setTemplateToView(null);
        }}
        onUseTemplate={(templateName) => {
          setSelectedTemplate(typeof templateName === 'string' ? templateName : templateName.name);
          setShowTemplateDetails(false);
          setTemplateToView(null);
        }}
        context="repo-creation"
      />
    </>
  );
};

export default UnifiedResourceModal;
export type { ExistingResourceData };
