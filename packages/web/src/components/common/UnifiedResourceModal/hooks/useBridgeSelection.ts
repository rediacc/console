import { useCallback, useEffect } from 'react';
import { UseFormReturn } from 'react-hook-form';
import { featureFlags } from '@/config/featureFlags';
import type { ResourceType } from '../index';

type ResourceFormValues = Record<string, unknown>;

interface DropdownData {
  bridgesByRegion?: Array<{
    regionName: string;
    bridges: Array<{ value: string; label: string }>;
  }>;
}

interface UseBridgeSelectionProps {
  resourceType: ResourceType;
  dropdownData?: DropdownData;
  form: UseFormReturn<ResourceFormValues>;
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
    [dropdownData]
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

  return {
    getFilteredBridges,
  };
};
