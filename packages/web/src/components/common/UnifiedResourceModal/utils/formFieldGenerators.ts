import type { FormFieldConfig } from '@/components/common/UnifiedResourceModal/components/ResourceFormWithVault';
import { featureFlags } from '@/config/featureFlags';
import { conditionalRequired, validationRules } from '@/platform/utils/formValidation';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
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
  teams?: { value: string; label: string }[];
  regions?: { value: string; label: string }[];
  machinesByTeam?: {
    teamName: string;
    machines: { value: string; label: string }[];
  }[];
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
  getFilteredBridges: (regionName: string | null) => { value: string; label: string }[];
  t: TypedTFunction;
}

// --- Constants and Mappings ---

const RESOURCE_TRANSLATION_KEYS: Record<ResourceType, string> = {
  storage: 'storage',
  repository: 'repositories',
  machine: 'machines',
  team: 'teams',
  region: 'regions',
  bridge: 'bridges',
  cluster: 'clusters',
  pool: 'pools',
  image: 'images',
  snapshot: 'snapshots',
  clone: 'clones',
};

const RESOURCE_NAME_LABELS: Record<ResourceType, string> = {
  machine: 'Machine',
  repository: 'Repository',
  storage: 'Storage',
  team: 'Team',
  region: 'Region',
  bridge: 'Bridge',
  cluster: 'Cluster',
  pool: 'Pool',
  image: 'Image',
  snapshot: 'Snapshot',
  clone: 'Clone',
};

// --- Helper Functions ---

const mapToOptions = (items?: { value: string; label: string }[]) =>
  Array.isArray(items) ? items.map((item) => ({ value: item.value, label: item.label })) : [];

const hasExistingGuid = (existingData?: Record<string, unknown>): boolean =>
  Boolean(
    existingData?.repositoryGuid &&
      typeof existingData.repositoryGuid === 'string' &&
      existingData.repositoryGuid.trim() !== ''
  );

const isCredentialOnlyMode = (
  existingData?: Record<string, unknown>,
  creationContext?: 'credentials-only' | 'normal'
): boolean => hasExistingGuid(existingData) || creationContext === 'credentials-only';

const getTeamMachines = (
  dropdownData: DropdownData | undefined,
  teamName: string
): { value: string; label: string }[] => {
  const machinesByTeam = dropdownData?.machinesByTeam ?? [];
  return machinesByTeam.find((team) => team.teamName === teamName)?.machines ?? [];
};

// --- Basic Field Creators ---

const createNameField = (resourceType: ResourceType, t: TypedTFunction): FormFieldConfig => ({
  name: `${resourceType}Name`,
  label: t(`${RESOURCE_TRANSLATION_KEYS[resourceType]}.${resourceType}Name`),
  placeholder: t(
    `${RESOURCE_TRANSLATION_KEYS[resourceType]}.placeholders.enter${resourceType.charAt(0).toUpperCase() + resourceType.slice(1)}Name`
  ),
  required: true,
  rules: validationRules.resourceName(RESOURCE_NAME_LABELS[resourceType]),
});

const createTeamField = (
  dropdownData: DropdownData | undefined,
  t: TypedTFunction
): FormFieldConfig => ({
  name: 'teamName',
  label: t('general.team'),
  placeholder: t('teams.placeholders.selectTeam'),
  required: true,
  type: 'select' as const,
  options: mapToOptions(dropdownData?.teams),
  rules: [validationRules.required('Team')],
});

const createRegionField = (
  dropdownData: DropdownData | undefined,
  t: TypedTFunction
): FormFieldConfig => ({
  name: 'regionName',
  label: t('general.region'),
  placeholder: t('regions.placeholders.selectRegion'),
  required: true,
  type: 'select' as const,
  options: mapToOptions(dropdownData?.regions) as { value: string; label: string }[],
  rules: [validationRules.required('Region')],
});

const createBridgeField = (
  getFormValue: (field: string) => string | undefined,
  getFilteredBridges: (regionName: string | null) => { value: string; label: string }[],
  t: TypedTFunction
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
    rules: [validationRules.required('Bridge')],
  };
};

// --- Repository-specific Field Creators ---

const createMachineSelectField = (
  teamMachines: { value: string; label: string }[],
  t: TypedTFunction,
  helperTextKey: string,
  isDisabled = false
): FormFieldConfig => ({
  name: 'machineName',
  label: t('machines:machine'),
  placeholder: t('machines:placeholders.selectMachine'),
  required: true,
  type: 'select' as const,
  options: teamMachines.map((machine) => ({
    value: machine.value,
    label: machine.label,
  })),
  disabled: isDisabled || teamMachines.length === 0,
  helperText: t(helperTextKey),
  rules: [conditionalRequired('Machine is required')],
});

const createSizeField = (t: TypedTFunction, helperTextKey: string): FormFieldConfig => ({
  name: 'size',
  label: t('repositories.size'),
  placeholder: t('repositories.placeholders.enterSize'),
  required: true,
  type: 'size' as const,
  sizeUnits: ['G', 'T'],
  helperText: t(helperTextKey),
  rules: [conditionalRequired('Size is required'), validationRules.sizeFormat()],
});

const getGuidHelperText = (guidExists: boolean, isRequired: boolean, t: TypedTFunction): string => {
  if (guidExists) {
    return t('repositories.guidHelperTextExisting');
  }
  if (isRequired) {
    return t('repositories.guidHelperTextNew');
  }
  return t('repositories.guidHelperText');
};

const createRepositoryGuidField = (
  existingData: Record<string, unknown> | undefined,
  t: TypedTFunction,
  isRequired: boolean
): FormFieldConfig => {
  const guidExists = hasExistingGuid(existingData);
  return {
    name: 'repositoryGuid',
    label: t('repositories.guid'),
    placeholder: isRequired ? undefined : t('repositories.placeholders.enterGuid'),
    type: 'text' as const,
    readOnly: guidExists,
    required: isRequired,
    helperText: getGuidHelperText(guidExists, isRequired, t),
    rules: isRequired
      ? [validationRules.required('Repository GUID'), validationRules.uuid()]
      : [validationRules.uuid()],
  };
};

// --- Ceph-specific Field Creators ---

const createClusterSelectField = (
  clusters: ClusterOption[],
  t: TypedTFunction
): FormFieldConfig => ({
  name: 'clusterName',
  label: t('ceph:pools.cluster'),
  placeholder: t('ceph:pools.selectCluster'),
  required: true,
  type: 'select' as const,
  options: clusters.map((cluster) => ({
    value: cluster.clusterName,
    label: cluster.clusterName,
  })),
  disabled: clusters.length === 0,
  rules: [validationRules.required('Cluster')],
});

const createPoolSelectField = (
  pools: PoolOption[],
  t: TypedTFunction,
  namespace: string
): FormFieldConfig => ({
  name: 'poolName',
  label: t(`ceph:${namespace}.pool`),
  placeholder: t(`ceph:${namespace}.selectPool`),
  required: true,
  type: 'select' as const,
  options: pools.map((pool) => ({
    value: pool.poolName,
    label: `${pool.poolName} (${pool.clusterName})`,
  })),
  disabled: pools.length === 0,
  rules: [validationRules.required('Pool')],
});

const createImageSelectField = (
  images: PoolImageOption[],
  selectedPoolName: string | undefined,
  t: TypedTFunction,
  namespace: string
): FormFieldConfig => ({
  name: 'imageName',
  label: t(`ceph:${namespace}.image`),
  placeholder: t(`ceph:${namespace}.selectImage`),
  required: true,
  type: 'select' as const,
  options: images.map((image) => ({
    value: image.imageName,
    label: image.imageName,
  })),
  disabled: !selectedPoolName || images.length === 0,
  rules: [validationRules.required('Image')],
});

const createSnapshotSelectField = (
  snapshots: SnapshotOption[],
  selectedImageName: string | undefined,
  t: TypedTFunction
): FormFieldConfig => ({
  name: 'snapshotName',
  label: t('ceph:clones.snapshot'),
  placeholder: t('ceph:clones.selectSnapshot'),
  required: true,
  type: 'select' as const,
  options: snapshots.map((snapshot) => ({
    value: snapshot.snapshotName,
    label: snapshot.snapshotName,
  })),
  disabled: !selectedImageName || snapshots.length === 0,
  rules: [validationRules.required('Snapshot')],
});

const createCephMachineSelectField = (
  machines: AvailableMachineOption[],
  t: TypedTFunction
): FormFieldConfig => ({
  name: 'machineName',
  label: t('ceph:images.machine'),
  placeholder: t('ceph:images.selectMachine'),
  required: true,
  type: 'select' as const,
  options: machines.map((machine) => ({
    value: machine.machineName,
    label: machine.machineName,
    disabled: machine.status !== 'AVAILABLE',
  })),
  disabled: machines.length === 0,
  helperText: machines.length === 0 ? t('machines:noMachinesFound') : undefined,
  rules: [validationRules.required('Machine')],
});

// --- Edit Mode Handlers ---

const getEditModeFields = (
  resourceType: ResourceType,
  nameField: FormFieldConfig,
  props: FormFieldGeneratorProps
): FormFieldConfig[] => {
  const { dropdownData, getFormValue, getFilteredBridges, t } = props;

  if (resourceType === 'machine') {
    const fields = [nameField, createRegionField(dropdownData, t)];
    if (featureFlags.isEnabled('bridgeManageEnabled')) {
      fields.push(createBridgeField(getFormValue, getFilteredBridges, t));
    }
    return fields;
  }

  if (resourceType === 'bridge') {
    return [nameField, createRegionField(dropdownData, t)];
  }

  if (resourceType === 'repository') {
    return [nameField];
  }

  return [nameField];
};

// --- Simple Mode Repository Fields ---

const getStringField = (
  existingData: Record<string, unknown> | undefined,
  field: string,
  defaultValue: string
): string => {
  const value = existingData?.[field];
  return typeof value === 'string' ? value : defaultValue;
};

const getArrayField = <T>(
  existingData: Record<string, unknown> | undefined,
  field: string
): T[] => {
  const value = existingData?.[field];
  return Array.isArray(value) ? (value as T[]) : [];
};

const getStringFieldOrFormValue = (
  getFormValue: (field: string) => string | undefined,
  existingData: Record<string, unknown> | undefined,
  field: string
): string | undefined => {
  const formValue = getFormValue(field);
  if (formValue) return formValue;

  const existingValue = existingData?.[field];
  return typeof existingValue === 'string' ? existingValue : undefined;
};

const getSimpleModeRepositoryFields = (
  nameField: FormFieldConfig,
  props: FormFieldGeneratorProps
): FormFieldConfig[] => {
  const { existingData, dropdownData, creationContext, t } = props;
  const fields: FormFieldConfig[] = [nameField];

  const isPrefilledMachine = existingData?.prefilledMachine;
  const isCredOnly = isCredentialOnlyMode(existingData, creationContext);
  const teamName = getStringField(existingData, 'teamName', 'Private Team');
  const teamMachines = getTeamMachines(dropdownData, teamName);

  if (!isPrefilledMachine && !isCredOnly) {
    fields.push(createMachineSelectField(teamMachines, t, 'repositories.machineHelperText'));
  }

  if (!isCredOnly) {
    fields.push(createSizeField(t, 'repositories.sizeHelperText'));
  }

  if (isCredOnly) {
    fields.push(createRepositoryGuidField(existingData, t, true));
  }

  return fields;
};

// --- Expert Mode Resource Field Generators (Strategy Pattern) ---

interface ResourceFieldGeneratorContext {
  nameField: FormFieldConfig;
  props: FormFieldGeneratorProps;
}

type ResourceFieldGenerator = (ctx: ResourceFieldGeneratorContext) => FormFieldConfig[];

const resolveSelectedTeamName = (
  getFormValue: (field: string) => string | undefined,
  existingData: Record<string, unknown> | undefined,
  teamFilter: string | string[] | undefined
): string => {
  const formTeamName = getFormValue('teamName');
  if (formTeamName) return formTeamName;

  const existingTeamName = existingData?.teamName;
  if (typeof existingTeamName === 'string') return existingTeamName;

  if (teamFilter) {
    return Array.isArray(teamFilter) ? teamFilter[0] : teamFilter;
  }

  return '';
};

const generateRepositoryFields: ResourceFieldGenerator = ({ nameField, props }) => {
  const { existingData, dropdownData, teamFilter, creationContext, isExpertMode, getFormValue, t } =
    props;
  const fields: FormFieldConfig[] = [nameField];

  const isPrefilledMachine = existingData?.prefilledMachine;
  const isCredOnly = isCredentialOnlyMode(existingData, creationContext);

  // Determine team name from various sources
  const selectedTeamName = resolveSelectedTeamName(getFormValue, existingData, teamFilter);
  const teamMachines = getTeamMachines(dropdownData, selectedTeamName);

  if (!isPrefilledMachine && !isCredOnly) {
    fields.push(
      createMachineSelectField(teamMachines, t, 'repositories.machineHelperTextRequired', false)
    );
  }

  if (!isCredOnly) {
    fields.push(createSizeField(t, 'repositories.sizeHelperTextRequired'));
  }

  if (isCredOnly) {
    fields.push(createRepositoryGuidField(existingData, t, true));
  } else if (isExpertMode) {
    fields.push(createRepositoryGuidField(existingData, t, false));
  }

  return fields;
};

const generateClusterFields: ResourceFieldGenerator = ({ nameField }) => [nameField];

const generatePoolFields: ResourceFieldGenerator = ({ nameField, props }) => {
  const { existingData, t } = props;
  const clusters = getArrayField<ClusterOption>(existingData, 'clusters');

  return [createClusterSelectField(clusters, t), nameField];
};

const generateImageFields: ResourceFieldGenerator = ({ nameField, props }) => {
  const { existingData, mode, t } = props;
  const pools = getArrayField<PoolOption>(existingData, 'pools');
  const machines = getArrayField<AvailableMachineOption>(existingData, 'availableMachines');

  const fields: FormFieldConfig[] = [createPoolSelectField(pools, t, 'images'), nameField];

  if (mode === 'create') {
    fields.push(createCephMachineSelectField(machines, t));
  }

  return fields;
};

const generateSnapshotFields: ResourceFieldGenerator = ({ nameField, props }) => {
  const { existingData, getFormValue, t } = props;
  const pools = getArrayField<PoolOption>(existingData, 'pools');
  const images = getArrayField<PoolImageOption>(existingData, 'images');
  const selectedPoolName = getStringFieldOrFormValue(getFormValue, existingData, 'poolName');

  const fields: FormFieldConfig[] = [];

  if (!existingData?.poolName) {
    fields.push(createPoolSelectField(pools, t, 'snapshots'));
  }

  fields.push(createImageSelectField(images, selectedPoolName, t, 'snapshots'));
  fields.push(nameField);

  return fields;
};

const generateCloneFields: ResourceFieldGenerator = ({ nameField, props }) => {
  const { existingData, getFormValue, t } = props;
  const pools = getArrayField<PoolOption>(existingData, 'pools');
  const images = getArrayField<PoolImageOption>(existingData, 'images');
  const snapshots = getArrayField<SnapshotOption>(existingData, 'snapshots');
  const selectedPoolName = getStringFieldOrFormValue(getFormValue, existingData, 'poolName');
  const selectedImageName = getStringFieldOrFormValue(getFormValue, existingData, 'imageName');

  const fields: FormFieldConfig[] = [];

  if (!existingData?.poolName) {
    fields.push(createPoolSelectField(pools, t, 'clones'));
  }

  if (!existingData?.imageName) {
    fields.push(createImageSelectField(images, selectedPoolName, t, 'clones'));
  }

  fields.push(createSnapshotSelectField(snapshots, selectedImageName, t));
  fields.push(nameField);

  return fields;
};

const generateMachineFields: ResourceFieldGenerator = ({ nameField }) => [nameField];

const generateBridgeFields: ResourceFieldGenerator = ({ nameField, props }) => {
  const { dropdownData, t } = props;
  return [createRegionField(dropdownData, t), nameField];
};

const generateSimpleResourceFields: ResourceFieldGenerator = ({ nameField }) => [nameField];

const RESOURCE_FIELD_GENERATORS: Partial<Record<ResourceType, ResourceFieldGenerator>> = {
  repository: generateRepositoryFields,
  cluster: generateClusterFields,
  pool: generatePoolFields,
  image: generateImageFields,
  snapshot: generateSnapshotFields,
  clone: generateCloneFields,
  machine: generateMachineFields,
  bridge: generateBridgeFields,
  team: generateSimpleResourceFields,
  region: generateSimpleResourceFields,
};

// --- Main Function ---

export const getFormFields = (props: FormFieldGeneratorProps): FormFieldConfig[] => {
  const { resourceType, mode, uiMode, isTeamPreselected, dropdownData, t } = props;
  const nameField = createNameField(resourceType, t);

  // Handle edit mode
  if (mode === 'edit') {
    return getEditModeFields(resourceType, nameField, props);
  }

  // Handle simple mode
  if (uiMode === 'simple') {
    if (resourceType === 'repository') {
      return getSimpleModeRepositoryFields(nameField, props);
    }
    return [nameField];
  }

  // Handle expert mode (create)
  const fields: FormFieldConfig[] = [];

  // Add team field for non-machine resources when team is not preselected
  if (!isTeamPreselected && resourceType !== 'machine') {
    fields.push(createTeamField(dropdownData, t));
  }

  // Use strategy pattern for resource-specific fields
  const generator = RESOURCE_FIELD_GENERATORS[resourceType];
  if (generator) {
    fields.push(...generator({ nameField, props }));
  } else {
    fields.push(nameField);
  }

  return fields.length ? fields : [nameField];
};
