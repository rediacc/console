import { useCallback } from 'react';
import { Modal } from 'antd';
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks';
import { templateService } from '@/services/templateService';
import {
  isBridgeFunction,
  safeValidateFunctionParams,
  getValidationErrors,
} from '@rediacc/shared/queue-vault';
import type { QueueFunction, QueueFunctionParameter } from '@rediacc/shared/types';

type FunctionParamValue = string | number | string[] | undefined;
type FunctionParams = Record<string, FunctionParamValue>;

// Helper: Check if template-selector is missing required value
const isTemplateSelectorMissing = (
  paramInfo: QueueFunctionParameter,
  selectedTemplates: string[]
): boolean => {
  return paramInfo.ui === 'template-selector' && selectedTemplates.length === 0;
};

// Helper: Check if regular parameter is missing value
const isRegularParamMissing = (
  paramName: string,
  paramInfo: QueueFunctionParameter,
  functionParams: FunctionParams
): boolean => {
  const paramValue = functionParams[paramName];
  if (paramValue === undefined || paramValue === '') return true;

  // For size parameters, also check if the value part is filled
  if (paramInfo.format === 'size' && paramInfo.units) {
    const valueParam = functionParams[`${paramName}_value`];
    return typeof valueParam !== 'number' || valueParam <= 0;
  }

  return false;
};

// Helper: Check if a single parameter is missing
const isParamMissing = (
  paramName: string,
  paramInfo: QueueFunctionParameter,
  functionParams: FunctionParams,
  selectedTemplates: string[]
): boolean => {
  if (isTemplateSelectorMissing(paramInfo, selectedTemplates)) return true;
  if (paramInfo.ui === 'template-selector') return false;
  return isRegularParamMissing(paramName, paramInfo, functionParams);
};

// Helper: Find all missing required parameters
const findMissingParams = (
  func: QueueFunction,
  functionParams: FunctionParams,
  hiddenParams: string[],
  selectedTemplates: string[]
): string[] => {
  const missingLabels = new Set<string>();

  for (const [paramName, paramInfo] of Object.entries(func.params)) {
    const isHidden = hiddenParams.includes(paramName);
    const isRequired = paramInfo.required;

    if (isHidden || !isRequired) continue;

    if (isParamMissing(paramName, paramInfo, functionParams, selectedTemplates)) {
      missingLabels.add(paramInfo.label ?? paramName);
    }
  }

  return [...missingLabels];
};

// Helper: Remove helper fields (_value, _unit) from params
const cleanParams = (functionParams: FunctionParams): FunctionParams => {
  return Object.entries(functionParams).reduce((acc, [key, value]) => {
    if (!key.endsWith('_value') && !key.endsWith('_unit')) {
      acc[key] = value;
    }
    return acc;
  }, {} as FunctionParams);
};

// Helper: Encode single template
const encodeSingleTemplate = async (templateId: string): Promise<string> => {
  return templateService.getEncodedTemplateDataById(templateId);
};

// Helper: Encode multiple templates into merged format
const encodeMultipleTemplates = async (templateIds: string[]): Promise<string> => {
  const templateDataList = await Promise.all(
    templateIds.map((templateId) => templateService.fetchTemplateData({ name: templateId }))
  );

  const mergedTemplate = {
    name: templateIds.join('+'),
    files: templateDataList.flatMap((template) => template.files as unknown[]),
  };

  const encoder = new TextEncoder();
  const uint8Array = encoder.encode(JSON.stringify(mergedTemplate));
  let binaryString = '';
  for (const byte of uint8Array) {
    binaryString += String.fromCharCode(byte);
  }
  return btoa(binaryString);
};

// Helper: Process templates and add to params
const processTemplates = async (
  func: QueueFunction,
  selectedTemplates: string[],
  allParams: FunctionParams
): Promise<void> => {
  if (selectedTemplates.length === 0) return;

  for (const [paramName, paramInfo] of Object.entries(func.params)) {
    if (paramInfo.ui !== 'template-selector') continue;

    const encodedTemplate =
      selectedTemplates.length === 1
        ? await encodeSingleTemplate(selectedTemplates[0])
        : await encodeMultipleTemplates(selectedTemplates);

    allParams[paramName] = encodedTemplate;
  }
};

interface UseFunctionSubmissionProps {
  selectedFunction: QueueFunction | null;
  functionParams: FunctionParams;
  functionPriority: number;
  functionDescription: string;
  selectedMachine: string;
  selectedTemplates: string[];
  showMachineSelection: boolean;
  hiddenParams: string[];
  defaultParams: FunctionParams;
  onSubmit: (functionData: {
    function: QueueFunction;
    params: FunctionParams;
    priority: number;
    description: string;
    selectedMachine?: string;
  }) => void;
}

export const useFunctionSubmission = ({
  selectedFunction,
  functionParams,
  functionPriority,
  functionDescription,
  selectedMachine,
  selectedTemplates,
  showMachineSelection,
  hiddenParams,
  defaultParams,
  onSubmit,
}: UseFunctionSubmissionProps) => {
  const { t } = useTranslation(['functions', 'resources']);
  const message = useMessage();

  const handleSubmit = useCallback(async () => {
    if (!selectedFunction) return;
    if (showMachineSelection && !selectedMachine) return;

    // Validate required parameters
    const missingParams = findMissingParams(
      selectedFunction,
      functionParams,
      hiddenParams,
      selectedTemplates
    );

    if (missingParams.length > 0) {
      Modal.error({
        title: t('functions:validationError'),
        content: t('functions:missingRequiredParams', { params: missingParams.join(', ') }),
      });
      return;
    }

    // Validate function parameters against Zod schemas (if available)
    if (isBridgeFunction(selectedFunction.name)) {
      const validationResult = safeValidateFunctionParams(selectedFunction.name, functionParams);
      if (!validationResult.success) {
        Modal.error({
          title: t('functions:validationError'),
          content: getValidationErrors(validationResult),
        });
        return;
      }
    }

    // Clean up and merge params
    const cleanedParams = cleanParams(functionParams);
    const allParams: FunctionParams = { ...defaultParams, ...cleanedParams };

    // Handle template encoding
    try {
      await processTemplates(selectedFunction, selectedTemplates, allParams);
    } catch (error) {
      console.error('Failed to encode templates:', error);
      message.error('resources:templates.failedToLoadTemplate');
      return;
    }

    onSubmit({
      function: selectedFunction,
      params: allParams,
      priority: functionPriority,
      description: functionDescription || selectedFunction.description,
      selectedMachine,
    });
  }, [
    selectedFunction,
    showMachineSelection,
    selectedMachine,
    hiddenParams,
    selectedTemplates,
    functionParams,
    defaultParams,
    functionPriority,
    functionDescription,
    onSubmit,
    t,
    message,
  ]);

  return { handleSubmit };
};
