import { useCallback } from 'react';
import type { QueueFunction } from '@/api/queries/queue';

type FunctionParamValue = string | number | string[] | undefined;
type FunctionParams = Record<string, FunctionParamValue>;

const toFunctionParamValue = (value: unknown): FunctionParamValue | undefined => {
  if (typeof value === 'string' || typeof value === 'number') {
    return value;
  }
  if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
    return value;
  }
  return undefined;
};

interface UseFunctionParametersProps {
  initialParams: FunctionParams;
  hiddenParams: string[];
  currentMachineName?: string;
}

export const useFunctionParameters = ({
  initialParams,
  hiddenParams,
  currentMachineName,
}: UseFunctionParametersProps) => {
  const initializeParams = useCallback(
    (func: QueueFunction) => {
      const defaultInitialParams: FunctionParams = {};

      Object.entries(func.params).forEach(([paramName, paramInfo]) => {
        // Check if we have an initial value from props
        if (initialParams[paramName] !== undefined && !hiddenParams.includes(paramName)) {
          defaultInitialParams[paramName] = initialParams[paramName];
          // For size parameters, also set the unit and value fields
          if (paramInfo.format === 'size' && paramInfo.units) {
            const match = String(initialParams[paramName]).match(/^(\d+)([%GT]?)$/);
            if (match) {
              const [, value, unit] = match;
              defaultInitialParams[`${paramName}_value`] = parseInt(value);
              defaultInitialParams[`${paramName}_unit`] =
                unit || (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0]);
            }
          }
        } else if (paramInfo.format === 'size' && paramInfo.units) {
          // Initialize with default values for size parameters
          if (typeof paramInfo.default === 'string') {
            const match = paramInfo.default.match(/^(\d+)([%GT]?)$/);
            if (match) {
              const [, value, unit] = match;
              defaultInitialParams[`${paramName}_value`] = parseInt(value);
              defaultInitialParams[`${paramName}_unit`] =
                unit || (paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0]);
              defaultInitialParams[paramName] = paramInfo.default;
            }
          } else {
            // Set default unit
            const defaultUnit = paramInfo.units[0] === 'percentage' ? '%' : paramInfo.units[0];
            defaultInitialParams[`${paramName}_unit`] = defaultUnit;
          }
        } else if (paramInfo.options && paramInfo.options.length > 0) {
          // Initialize dropdown parameters with default value
          const defaultValue = toFunctionParamValue(paramInfo.default) ?? paramInfo.options[0];
          defaultInitialParams[paramName] = defaultValue;
        } else {
          // Initialize other parameters with default value
          const defaultValue = toFunctionParamValue(paramInfo.default);
          if (typeof defaultValue !== 'undefined') {
            defaultInitialParams[paramName] = defaultValue;
          }
        }

        // Special handling for destination-dropdown: set current machine as default
        if (paramInfo.ui === 'destination-dropdown' && currentMachineName) {
          // Check if there's a destinationType parameter with value 'machine'
          const destinationTypeParam = func.params['destinationType'];
          const destinationDefault =
            typeof destinationTypeParam.default === 'string'
              ? destinationTypeParam.default
              : undefined;
          if (
            defaultInitialParams['destinationType'] === 'machine' ||
            destinationDefault === 'machine'
          ) {
            defaultInitialParams[paramName] = currentMachineName;
          }
        }
      });

      return defaultInitialParams;
    },
    [initialParams, hiddenParams, currentMachineName]
  );

  return { initializeParams };
};
