import { useCallback, useEffect } from 'react';
import { featureFlags } from '@/config/featureFlags';
import type { ResourceType } from '../index';
import type { FormInstance } from 'antd/es/form';

interface DropdownData {
  bridgesByRegion?: {
    regionName: string;
    bridges: { value: string; label: string }[];
  }[];
}

interface UseBridgeSelectionProps {
  resourceType: ResourceType;
  dropdownData?: DropdownData;
  form: FormInstance;
  getFormValue: (field: string) => string | undefined;
}

export const useBridgeSelection = ({
  resourceType,
  dropdownData,
  form,
  getFormValue,
}: UseBridgeSelectionProps) => {
  // Get filtered bridges based on selected region
  const getFilteredBridges = useCallback(
    (regionName: string | null): { value: string; label: string }[] => {
      if (!regionName || !dropdownData?.bridgesByRegion) return [];

      const bridgesByRegion = dropdownData.bridgesByRegion ?? [];
      const regionData = bridgesByRegion.find((region) => region.regionName === regionName);
      const bridges = regionData?.bridges ?? [];
      return bridges.map((bridge) => ({
        value: bridge.value,
        label: bridge.label,
      }));
    },
    [dropdownData]
  );

  // Clear bridge selection when region changes, or auto-select if bridge disabled
  useEffect(() => {
    if (resourceType !== 'machine') return;

    // For Ant Design Form, we use onValuesChange in the parent component instead
    // This effect is kept for the auto-select behavior when bridge feature is disabled
    const handleRegionChange = () => {
      const regionValue = getFormValue('regionName');
      if (!regionValue) return;

      const currentBridge = getFormValue('bridgeName');
      const filteredBridges = getFilteredBridges(regionValue);

      // If bridge management UI is hidden, auto-select first available bridge
      if (!featureFlags.isEnabled('bridgeManageEnabled')) {
        if (filteredBridges.length > 0) {
          form.setFieldValue('bridgeName', filteredBridges[0].value);
        }
      } else if (currentBridge && !filteredBridges.find((b) => b.value === currentBridge)) {
        // Normal behavior: clear bridge if it's not valid for the new region
        form.setFieldValue('bridgeName', '');
      }
    };

    // Initial check
    handleRegionChange();
  }, [form, resourceType, getFilteredBridges, getFormValue]);

  return {
    getFilteredBridges,
  };
};
