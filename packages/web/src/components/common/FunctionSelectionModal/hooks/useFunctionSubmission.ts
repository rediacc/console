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
import type { QueueFunction } from '@rediacc/shared/types';

type FunctionParamValue = string | number | string[] | undefined;
type FunctionParams = Record<string, FunctionParamValue>;

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
    const missingParams: string[] = [];
    Object.entries(selectedFunction.params)
      .filter(([paramName]) => !hiddenParams.includes(paramName))
      .forEach(([paramName, paramInfo]) => {
        if (paramInfo.required) {
          // Special handling for template-selector - check selectedTemplates state
          if (paramInfo.ui === 'template-selector') {
            if (selectedTemplates.length === 0) {
              missingParams.push(paramInfo.label ?? paramName);
            }
          } else {
            const paramValue = functionParams[paramName];

            // Check if parameter has a value
            if (paramValue === undefined || paramValue === '') {
              missingParams.push(paramInfo.label ?? paramName);
            }

            // For size parameters, also check if the value part is filled
            if (paramInfo.format === 'size' && paramInfo.units) {
              const valueParam = functionParams[`${paramName}_value`];
              if (typeof valueParam !== 'number' || valueParam <= 0) {
                if (!missingParams.includes(paramInfo.label ?? paramName)) {
                  missingParams.push(paramInfo.label ?? paramName);
                }
              }
            }
          }
        }
      });

    // If there are missing parameters, show error and return
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

    // Clean up the params - remove the helper _value and _unit fields
    const cleanedParams = Object.entries(functionParams).reduce((acc, [key, value]) => {
      if (!key.endsWith('_value') && !key.endsWith('_unit')) {
        acc[key] = value;
      }
      return acc;
    }, {} as FunctionParams);

    // Merge visible params with default params
    const allParams: FunctionParams = { ...defaultParams, ...cleanedParams };

    // Handle template encoding for template-selector parameters
    if (selectedTemplates.length > 0) {
      for (const [paramName, paramInfo] of Object.entries(selectedFunction.params)) {
        if (paramInfo.ui === 'template-selector') {
          try {
            if (selectedTemplates.length === 1) {
              // Single template: use the existing service method
              const encodedTemplate = await templateService.getEncodedTemplateDataById(
                selectedTemplates[0]
              );
              allParams[paramName] = encodedTemplate;
            } else {
              // Multiple templates: fetch and merge them
              const templateDataList = await Promise.all(
                selectedTemplates.map((templateId) =>
                  templateService.fetchTemplateData({ name: templateId })
                )
              );

              // Merge all templates into one structure
              const mergedTemplate = {
                name: selectedTemplates.join('+'),
                files: templateDataList.flatMap((template) => template.files as unknown[]),
              };

              // Encode the merged template using the same method as templateService
              const encoder = new TextEncoder();
              const uint8Array = encoder.encode(JSON.stringify(mergedTemplate));
              let binaryString = '';
              for (const byte of uint8Array) {
                binaryString += String.fromCharCode(byte);
              }
              const encodedTemplate = btoa(binaryString);

              allParams[paramName] = encodedTemplate;
            }
          } catch (error) {
            console.error('Failed to encode templates:', error);
            message.error('resources:templates.failedToLoadTemplate');
            return;
          }
        }
      }
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
