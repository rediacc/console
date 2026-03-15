import type { QueueFunction } from '@rediacc/shared/types';
import { useCallback, useMemo } from 'react';

type FunctionParamValue = string | number | string[] | undefined;
type FunctionParams = Record<string, FunctionParamValue>;

interface UseFunctionSelectionProps {
  localizedFunctions: Record<string, QueueFunction>;
  allowedCategories?: string[];
  functionSearchTerm: string;
  onSelectFunction: (func: QueueFunction, params: FunctionParams) => void;
  initializeParams: (func: QueueFunction) => FunctionParams;
}

export const useFunctionSelection = ({
  localizedFunctions,
  allowedCategories,
  functionSearchTerm,
  onSelectFunction,
  initializeParams,
}: UseFunctionSelectionProps) => {
  // Filter functions based on allowed categories and search term
  const filteredFunctions = useMemo(() => {
    let functions = Object.values(localizedFunctions);

    // Filter by allowed categories if specified
    if (allowedCategories && allowedCategories.length > 0) {
      functions = functions.filter((func) => allowedCategories.includes(func.category));
    }

    // Filter by search term
    if (functionSearchTerm) {
      const searchLower = functionSearchTerm.toLowerCase();
      functions = functions.filter(
        (func) =>
          func.name.toLowerCase().includes(searchLower) ||
          func.description.toLowerCase().includes(searchLower)
      );
    }

    return functions;
  }, [localizedFunctions, allowedCategories, functionSearchTerm]);

  // Group functions by category
  const functionsByCategory = useMemo(() => {
    return filteredFunctions.reduce<Record<string, QueueFunction[]>>((acc, func) => {
      const categoryFuncs = acc[func.category] ?? [];
      categoryFuncs.push(func);
      acc[func.category] = categoryFuncs;
      return acc;
    }, {});
  }, [filteredFunctions]);

  // Handler for selecting a function
  const handleSelectFunction = useCallback(
    (func: QueueFunction) => {
      const params = initializeParams(func);
      onSelectFunction(func, params);
    },
    [initializeParams, onSelectFunction]
  );

  return {
    filteredFunctions,
    functionsByCategory,
    handleSelectFunction,
  };
};
