// Re-export from generated file (single source of truth from renet)
export {
  FUNCTION_DEFINITIONS,
  FUNCTION_CATEGORIES,
  type FunctionDefinition,
  type FunctionParameterDefinition,
  type FunctionCategory,
  type CheckboxOption,
  type UIType,
} from './functions.generated';

// Default export for backwards compatibility
import { FUNCTION_DEFINITIONS, FUNCTION_CATEGORIES } from './functions.generated';
export default { functions: FUNCTION_DEFINITIONS, categories: FUNCTION_CATEGORIES };
