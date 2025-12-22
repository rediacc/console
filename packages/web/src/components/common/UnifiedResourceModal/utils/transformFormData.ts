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

export const transformFormData = async (
  data: ResourceFormValues,
  options: TransformFormDataOptions
): Promise<ResourceFormValues> => {
  const { resourceType, mode, uiMode, existingData, selectedTemplate, autoSetupEnabled } = options;

  // Set Simple mode defaults
  if (uiMode === 'simple' && mode === 'create') {
    const defaults: ResourceFormValues = {};

    if (!data.teamName) {
      defaults.teamName = existingData?.teamName || 'Private Team';
    }

    if (resourceType === 'machine') {
      defaults.regionName = 'Default Region';
      defaults.bridgeName = 'Global Bridges';
    }

    Object.assign(data, defaults);
  }

  // Repository-specific transformations
  if (resourceType === 'repository') {
    // Ensure machine name is included when creating from machine
    if (existingData?.machineName && existingData?.prefilledMachine) {
      data.machineName = existingData.machineName;
      if (existingData?.teamName && !data.teamName) {
        data.teamName = existingData.teamName;
      }
    }

    // Add template parameter
    if (mode === 'create' && selectedTemplate) {
      try {
        data.tmpl = await templateService.getEncodedTemplateDataById(selectedTemplate);
      } catch (error) {
        console.error('Failed to load template:', error);
      }
    }

    // Always keep repository open after creation
    if (mode === 'create') {
      data.keep_open = true;
    }

    // Add repositoryGuid for credential-only creation
    if (mode === 'create' && existingData?.repositoryGuid) {
      data.repositoryGuid = existingData.repositoryGuid;
    }
  }

  // Machine-specific transformations
  if (resourceType === 'machine' && mode === 'create') {
    data.autoSetup = autoSetupEnabled;
  }

  return data;
};
