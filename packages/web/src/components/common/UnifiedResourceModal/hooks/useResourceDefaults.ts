import { useEffect } from 'react';
import type { CompanyDropdownData } from '@rediacc/shared/types';
import type { ExistingResourceData, ResourceFormValues, ResourceType } from '../types';
import type { FormInstance } from 'antd/es/form';

interface UseResourceDefaultsOptions {
  open: boolean;
  mode: 'create' | 'edit' | 'vault';
  resourceType: ResourceType;
  form: FormInstance<ResourceFormValues>;
  dropdownData?: CompanyDropdownData;
  existingData?: ExistingResourceData;
  teamFilter?: string | string[];
  setSelectedTemplate: (template: string | null) => void;
}

const getSingleTeamFromFilter = (teamFilter: string | string[] | undefined): string | undefined => {
  if (!teamFilter) {
    return undefined;
  }

  if (Array.isArray(teamFilter) && teamFilter.length === 1) {
    return teamFilter[0];
  }

  if (!Array.isArray(teamFilter)) {
    return teamFilter;
  }

  return undefined;
};

const setRepositoryDefaults = (
  form: FormInstance<ResourceFormValues>,
  existingData?: ExistingResourceData,
  setSelectedTemplate?: (template: string | null) => void
) => {
  // Reset template selection for repositories (unless preselected)
  const preselected =
    existingData &&
    typeof (existingData as Record<string, unknown>).preselectedTemplate === 'string'
      ? (existingData as Record<string, string>).preselectedTemplate || null
      : null;

  if (setSelectedTemplate) {
    setSelectedTemplate(preselected);
  }

  // Set prefilled machine if provided
  if (existingData?.machineName) {
    form.setFieldValue('machineName', existingData.machineName);
  }
};

const setMachineDefaults = (
  form: FormInstance<ResourceFormValues>,
  dropdownData?: CompanyDropdownData
) => {
  if (!dropdownData?.regions || dropdownData.regions.length === 0) {
    return;
  }

  const firstRegion = dropdownData.regions[0].value;
  form.setFieldValue('regionName', firstRegion);

  const regionBridges = dropdownData.bridgesByRegion.find(
    (region: { regionName: string }) => region.regionName === firstRegion
  );

  if (regionBridges?.bridges && regionBridges.bridges.length > 0) {
    const firstBridge = regionBridges.bridges[0].value;
    form.setFieldValue('bridgeName', firstBridge);
  }
};

export const useResourceDefaults = (options: UseResourceDefaultsOptions): void => {
  const {
    open,
    mode,
    resourceType,
    form,
    dropdownData,
    existingData,
    teamFilter,
    setSelectedTemplate,
  } = options;

  useEffect(() => {
    if (!open || mode !== 'create') {
      return;
    }

    // Set team if available
    const singleTeam = getSingleTeamFromFilter(teamFilter);
    const teamName = existingData?.teamName ?? singleTeam;
    if (teamName) {
      form.setFieldValue('teamName', teamName);
    }

    // Resource-specific defaults
    if (resourceType === 'repository') {
      setRepositoryDefaults(form, existingData, setSelectedTemplate);
    } else if (resourceType === 'machine') {
      setMachineDefaults(form, dropdownData);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mode, resourceType, teamFilter, dropdownData, existingData]);
};
