import { useCallback } from 'react';
import type { QueueFunction, QueueFunctionParameter } from '@rediacc/shared/types';

type FunctionParamValue = string | number | string[] | undefined;
type FunctionParams = Record<string, FunctionParamValue>;

const SIZE_PATTERN = /^(\d+)([%GT]?)$/;

const toFunctionParamValue = (value: unknown): FunctionParamValue | undefined => {
  if (typeof value === 'string' || typeof value === 'number') {
    return value;
  }
  if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
    return value;
  }
  return undefined;
};

const getDefaultUnit = (units: string[]): string => (units[0] === 'percentage' ? '%' : units[0]);

// Helper: Parse size value string and extract value and unit
const parseSizeValue = (
  sizeString: string,
  units: string[]
): { value: number; unit: string } | null => {
  const match = SIZE_PATTERN.exec(sizeString);
  if (!match) return null;
  const [, value, unit] = match;
  return {
    value: Number.parseInt(value),
    unit: unit || getDefaultUnit(units),
  };
};

// Helper: Initialize size parameter from initial props value
const initSizeParamFromInitial = (
  params: FunctionParams,
  paramName: string,
  initialValue: FunctionParamValue,
  units: string[]
): void => {
  params[paramName] = initialValue;
  const parsed = parseSizeValue(String(initialValue), units);
  if (parsed) {
    params[`${paramName}_value`] = parsed.value;
    params[`${paramName}_unit`] = parsed.unit;
  }
};

// Helper: Initialize size parameter from default value
const initSizeParamFromDefault = (
  params: FunctionParams,
  paramName: string,
  paramInfo: QueueFunctionParameter
): void => {
  const units = paramInfo.units ?? [];
  if (typeof paramInfo.default === 'string') {
    const parsed = parseSizeValue(paramInfo.default, units);
    if (parsed) {
      params[`${paramName}_value`] = parsed.value;
      params[`${paramName}_unit`] = parsed.unit;
      params[paramName] = paramInfo.default;
    }
    return;
  }
  // Set default unit only
  params[`${paramName}_unit`] = getDefaultUnit(units);
};

// Helper: Initialize dropdown parameter
const initDropdownParam = (
  params: FunctionParams,
  paramName: string,
  paramInfo: QueueFunctionParameter
): void => {
  const options = paramInfo.options ?? [];
  const defaultValue = toFunctionParamValue(paramInfo.default) ?? options[0];
  params[paramName] = defaultValue;
};

// Helper: Initialize other parameter types
const initOtherParam = (
  params: FunctionParams,
  paramName: string,
  paramInfo: QueueFunctionParameter
): void => {
  const defaultValue = toFunctionParamValue(paramInfo.default);
  if (typeof defaultValue !== 'undefined') {
    params[paramName] = defaultValue;
  }
};

// Helper: Handle destination-dropdown special case
const handleDestinationDropdown = (
  params: FunctionParams,
  paramName: string,
  paramInfo: QueueFunctionParameter,
  func: QueueFunction,
  currentMachineName: string | undefined
): void => {
  if (paramInfo.ui !== 'destination-dropdown' || !currentMachineName) return;

  const destinationTypeParam = func.params['destinationType'] as QueueFunctionParameter | undefined;
  if (!destinationTypeParam) return;

  const destinationDefault =
    typeof destinationTypeParam.default === 'string' ? destinationTypeParam.default : undefined;
  const isMachineDestination =
    params['destinationType'] === 'machine' || destinationDefault === 'machine';

  if (isMachineDestination) {
    params[paramName] = currentMachineName;
  }
};

// Helper: Initialize a single parameter based on its type
const initializeParameter = (
  result: FunctionParams,
  paramName: string,
  paramInfo: QueueFunctionParameter,
  initialParams: FunctionParams,
  hiddenParams: string[]
): void => {
  const hasInitialValue = initialParams[paramName] !== undefined;
  const isHidden = hiddenParams.includes(paramName);
  const isSizeParam = paramInfo.format === 'size' && paramInfo.units;
  const hasOptions = paramInfo.options && paramInfo.options.length > 0;

  // Handle initial value from props
  if (hasInitialValue && !isHidden) {
    if (isSizeParam) {
      initSizeParamFromInitial(result, paramName, initialParams[paramName], paramInfo.units!);
    } else {
      result[paramName] = initialParams[paramName];
    }
    return;
  }

  // Handle size parameter defaults
  if (isSizeParam) {
    initSizeParamFromDefault(result, paramName, paramInfo);
    return;
  }

  // Handle dropdown parameter defaults
  if (hasOptions) {
    initDropdownParam(result, paramName, paramInfo);
    return;
  }

  // Handle other parameter types
  initOtherParam(result, paramName, paramInfo);
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
      const result: FunctionParams = {};

      for (const [paramName, paramInfo] of Object.entries(func.params)) {
        initializeParameter(result, paramName, paramInfo, initialParams, hiddenParams);
        handleDestinationDropdown(result, paramName, paramInfo, func, currentMachineName);
      }

      return result;
    },
    [initialParams, hiddenParams, currentMachineName]
  );

  return { initializeParams };
};
