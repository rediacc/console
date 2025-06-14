import { useTranslation } from 'react-i18next';
import functionDefinitions from '@/data/functions.json';

// Base function definition without translatable content
export interface FunctionDefinition {
  name: string;
  category: string;
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
  const getLocalizedCategories = () => {
    const categories: Record<string, { name: string; description: string }> = {};
    
    FUNCTION_CATEGORIES.forEach(category => {
      categories[category] = {
        name: t(`categories.${category}.name`),
        description: t(`categories.${category}.description`)
      };
    });

    return categories;
  };

  // Get localized function data
  const getLocalizedFunction = (functionName: string) => {
    const funcDef = FUNCTION_DEFINITIONS[functionName];
    if (!funcDef) return null;

    const localizedFunc = {
      ...funcDef,
      description: t(`functions.${functionName}.description`),
      requirements: funcDef.requirements || {},
      params: {} as Record<string, any>
    };

    // Localize parameters
    if (funcDef.params) {
      Object.entries(funcDef.params).forEach(([paramName, paramDef]) => {
        localizedFunc.params[paramName] = {
          ...paramDef,
          label: t(`functions.${functionName}.params.${paramName}.label`),
          help: t(`functions.${functionName}.params.${paramName}.help`)
        };
      });
    }

    return localizedFunc;
  };

  // Get all localized functions
  const getLocalizedFunctions = () => {
    const functions: Record<string, any> = {};
    
    Object.keys(FUNCTION_DEFINITIONS).forEach(functionName => {
      functions[functionName] = getLocalizedFunction(functionName);
    });

    return functions;
  };

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
  const categories: Record<string, any> = {};
  const functions: Record<string, any> = {};

  // Process categories
  FUNCTION_CATEGORIES.forEach(category => {
    categories[category] = {
      name: t(`functions:categories.${category}.name`),
      description: t(`functions:categories.${category}.description`)
    };
  });

  // Process functions
  Object.entries(FUNCTION_DEFINITIONS).forEach(([functionName, funcDef]) => {
    functions[functionName] = {
      name: functionName,
      category: funcDef.category,
      requirements: funcDef.requirements || {},
      description: t(`functions:functions.${functionName}.description`),
      params: {} as Record<string, any>
    };

    // Process parameters
    if (funcDef.params) {
      Object.entries(funcDef.params).forEach(([paramName, paramDef]) => {
        functions[functionName].params[paramName] = {
          ...paramDef,
          help: t(`functions:functions.${functionName}.params.${paramName}.help`)
        };
      });
    }
  });

  return { categories, functions };
}