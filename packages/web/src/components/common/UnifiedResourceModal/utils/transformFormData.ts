import { templateService } from '@/services/templateService';
import type { ExistingResourceData, ResourceFormValues, ResourceType } from '../types';

interface TransformFormDataOptions {
  resourceType: ResourceType;
  mode: 'create' | 'edit' | 'vault';
  uiMode: 'simple' | 'expert';
  existingData?: ExistingResourceData;
  selectedTemplate: string | null;
  autoSetupEnabled: boolean;
}

// --- Helper Functions ---

const applySimpleModeDefaults = (
  data: ResourceFormValues,
  resourceType: ResourceType,
  existingData?: ExistingResourceData
): void => {
  data.teamName ??= existingData?.teamName;

  if (resourceType === 'machine') {
    data.regionName = 'Default Region';
    data.bridgeName = 'Global Bridges';
  }
};

const applyRepositoryMachineData = (
  data: ResourceFormValues,
  existingData?: ExistingResourceData
): void => {
  if (!existingData?.machineName || !existingData.prefilledMachine) {
    return;
  }

  data.machineName = existingData.machineName;

  if (existingData.teamName && !data.teamName) {
    data.teamName = existingData.teamName;
  }
};

const applyRepositoryTemplate = async (
  data: ResourceFormValues,
  selectedTemplate: string | null
): Promise<void> => {
  if (!selectedTemplate) {
    return;
  }

  try {
    data.tmpl = await templateService.getEncodedTemplateDataById(selectedTemplate);
  } catch (error) {
    console.error('Failed to load template:', error);
  }
};

const applyRepositoryGuid = (
  data: ResourceFormValues,
  existingData?: ExistingResourceData
): void => {
  if (existingData?.repositoryGuid) {
    data.repositoryGuid = existingData.repositoryGuid;
  }
};

const applyRepositoryTransformations = async (
  data: ResourceFormValues,
  mode: TransformFormDataOptions['mode'],
  existingData?: ExistingResourceData,
  selectedTemplate?: string | null
): Promise<void> => {
  applyRepositoryMachineData(data, existingData);

  if (mode === 'create') {
    await applyRepositoryTemplate(data, selectedTemplate ?? null);
    data.keep_open = true;
    applyRepositoryGuid(data, existingData);
  }
};

const applyMachineTransformations = (data: ResourceFormValues, autoSetupEnabled: boolean): void => {
  data.autoSetup = autoSetupEnabled;
};

// --- Main Function ---

export const transformFormData = async (
  data: ResourceFormValues,
  options: TransformFormDataOptions
): Promise<ResourceFormValues> => {
  const { resourceType, mode, uiMode, existingData, selectedTemplate, autoSetupEnabled } = options;

  // Apply simple mode defaults
  if (uiMode === 'simple' && mode === 'create') {
    applySimpleModeDefaults(data, resourceType, existingData);
  }

  // Apply resource-specific transformations
  if (resourceType === 'repository') {
    await applyRepositoryTransformations(data, mode, existingData, selectedTemplate);
  }

  if (resourceType === 'machine' && mode === 'create') {
    applyMachineTransformations(data, autoSetupEnabled);
  }

  return data;
};
