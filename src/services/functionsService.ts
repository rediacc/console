import { useTranslation } from 'react-i18next';
import functionDefinitions from '@/data/functions.json';

// Base function definition without translatable content
export interface FunctionDefinition {
  name: string;
  category: string;
  showInMenu?: boolean;
  requirements?: FunctionRequirements;
  params?: Record<string, FunctionParam>;
}

export interface FunctionRequirements {
  machine?: boolean;
  team?: boolean;
  company?: boolean;
  repository?: boolean;
  storage?: boolean;
  plugin?: boolean;
  bridge?: boolean;
}

export interface FunctionParam {
  type: string;
  required?: boolean;
  default?: string;
  format?: string;
  units?: string[];
  help?: string;
  label?: string;
  options?: string[]; // For dropdown parameters
}

// Import function definitions from JSON
export const FUNCTION_DEFINITIONS: Record<string, FunctionDefinition> = functionDefinitions.functions;
export const FUNCTION_CATEGORIES: string[] = functionDefinitions.categories;

// Hook to get localized function data
export function useLocalizedFunctions() {
  const { t } = useTranslation('functions');

  // Get localized category data
  const getLocalizedCategories = () => 
    Object.fromEntries(
      FUNCTION_CATEGORIES.map(category => [
        category,
        {
          name: t(`categories.${category}.name`),
          description: t(`categories.${category}.description`)
        }
      ])
    );

  // Get localized function data
  const getLocalizedFunction = (functionName: string) => {
    const funcDef = FUNCTION_DEFINITIONS[functionName];
    if (!funcDef) return null;

    return {
      ...funcDef,
      description: t(`functions.${functionName}.description`),
      showInMenu: funcDef.showInMenu !== false, // Default to true if not specified
      requirements: funcDef.requirements || {},
      params: funcDef.params ? Object.fromEntries(
        Object.entries(funcDef.params).map(([paramName, paramDef]) => [
          paramName,
          {
            ...paramDef,
            label: t(`functions.${functionName}.params.${paramName}.label`),
            help: t(`functions.${functionName}.params.${paramName}.help`)
          }
        ])
      ) : {}
    };
  };

  // Get all localized functions
  const getLocalizedFunctions = () => 
    Object.fromEntries(
      Object.keys(FUNCTION_DEFINITIONS).map(name => [name, getLocalizedFunction(name)])
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
    getFunctionsByCategory
  };
}

// Export function to get raw function data with translations
export function getFunctionsWithTranslations(t: any) {
  const categories = Object.fromEntries(
    FUNCTION_CATEGORIES.map(category => [
      category,
      {
        name: t(`functions:categories.${category}.name`),
        description: t(`functions:categories.${category}.description`)
      }
    ])
  );

  const functions = Object.fromEntries(
    Object.entries(FUNCTION_DEFINITIONS).map(([functionName, funcDef]) => [
      functionName,
      {
        name: functionName,
        category: funcDef.category,
        requirements: funcDef.requirements || {},
        description: t(`functions:functions.${functionName}.description`),
        params: funcDef.params ? Object.fromEntries(
          Object.entries(funcDef.params).map(([paramName, paramDef]) => [
            paramName,
            {
              ...paramDef,
              help: t(`functions:functions.${functionName}.params.${paramName}.help`)
            }
          ])
        ) : {}
      }
    ])
  );

  return { categories, functions };
}