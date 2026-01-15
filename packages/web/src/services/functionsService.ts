import {
  FUNCTION_CATEGORIES,
  FUNCTION_DEFINITIONS,
  type FunctionDefinition,
} from '@rediacc/shared/queue-vault/data/definitions';
import { isBridgeFunction } from '@rediacc/shared/queue-vault/data/functions.generated';
import { useTranslation } from 'react-i18next';

// Re-export for backwards compatibility
export { FUNCTION_DEFINITIONS };

// Hook to get localized function data
export function useLocalizedFunctions() {
  const { t } = useTranslation('functions');

  // Get localized category data
  const getLocalizedCategories = () =>
    Object.fromEntries(
      [...FUNCTION_CATEGORIES].map((category) => [
        category,
        {
          name: t(`categories.${category}.name`),
          description: t(`categories.${category}.description`),
        },
      ])
    );

  // Get localized function data
  const getLocalizedFunction = (functionName: string) => {
    if (!isBridgeFunction(functionName)) return null;
    const funcDef: FunctionDefinition = FUNCTION_DEFINITIONS[functionName];

    return {
      ...funcDef,
      description: t(`functions.${functionName}.description`),
      showInMenu: funcDef.showInMenu !== false, // Default to true if not specified
      requirements: funcDef.requirements,
      params: Object.fromEntries(
        Object.entries(funcDef.params).map(([paramName, paramDef]) => [
          paramName,
          {
            ...paramDef,
            label: t(`functions.${functionName}.params.${paramName}.label`),
            help: t(`functions.${functionName}.params.${paramName}.help`),
          },
        ])
      ),
    };
  };

  // Get all localized functions
  const getLocalizedFunctions = () =>
    Object.fromEntries(
      Object.keys(FUNCTION_DEFINITIONS).map((name) => [name, getLocalizedFunction(name)])
    );

  // Get functions by category
  const getFunctionsByCategory = (category: string) => {
    return Object.entries(FUNCTION_DEFINITIONS)
      .filter(([_, funcDef]) => funcDef.category === category)
      .map(([name]) => getLocalizedFunction(name))
      .filter(Boolean);
  };

  return {
    categories: getLocalizedCategories(),
    functions: getLocalizedFunctions(),
    getFunction: getLocalizedFunction,
    getFunctionsByCategory,
  };
}
