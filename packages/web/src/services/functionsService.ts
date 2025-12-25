import { useTranslation } from 'react-i18next';
import functionDefinitions from '@rediacc/shared/queue-vault/data/definitions';

// Base function definition without translatable content
interface FunctionDefinition {
  name: string;
  category: string;
  showInMenu?: boolean;
  requirements?: FunctionRequirements;
  params?: Record<string, FunctionParam>;
}

interface FunctionRequirements {
  machine?: boolean;
  team?: boolean;
  company?: boolean;
  repository?: boolean;
  storage?: boolean;
  plugin?: boolean;
  bridge?: boolean;
}

interface FunctionParam {
  type: string;
  required?: boolean;
  default?: string;
  format?: string;
  units?: string[];
  help?: string;
  label?: string;
  options?: string[]; // For dropdown parameters
  ui?: string; // UI type specification (e.g., 'dropdown', 'repo-dropdown', 'destination-dropdown')
}

// Import function definitions from JSON
export const FUNCTION_DEFINITIONS: Record<string, FunctionDefinition> =
  functionDefinitions.functions;
const FUNCTION_CATEGORIES: string[] = functionDefinitions.categories;

// Hook to get localized function data
export function useLocalizedFunctions() {
  const { t } = useTranslation('functions');

  // Get localized category data
  const getLocalizedCategories = () =>
    Object.fromEntries(
      FUNCTION_CATEGORIES.map((category) => [
        category,
        {
          name: t(`categories.${category}.name`),
          description: t(`categories.${category}.description`),
        },
      ])
    );

  // Get localized function data
  const getLocalizedFunction = (functionName: string) => {
    const funcDef = FUNCTION_DEFINITIONS[functionName] as FunctionDefinition | undefined;
    if (funcDef === undefined) return null;

    return {
      ...funcDef,
      description: t(`functions.${functionName}.description`),
      showInMenu: funcDef.showInMenu !== false, // Default to true if not specified
      requirements: funcDef.requirements ?? {},
      params: funcDef.params
        ? Object.fromEntries(
            Object.entries(funcDef.params).map(([paramName, paramDef]) => [
              paramName,
              {
                ...paramDef,
                label: t(`functions.${functionName}.params.${paramName}.label`),
                help: t(`functions.${functionName}.params.${paramName}.help`),
              },
            ])
          )
        : {},
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
