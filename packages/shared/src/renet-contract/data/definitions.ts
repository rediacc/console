// Re-export from generated file (single source of truth from renet)
export {
  type CheckboxOption,
  FUNCTION_CATEGORIES,
  FUNCTION_DEFINITIONS,
  type FunctionCategory,
  type FunctionDefinition,
  type FunctionParameterDefinition,
  type UIType,
} from './functions.generated.js';

// Default export for backwards compatibility
import { FUNCTION_CATEGORIES, FUNCTION_DEFINITIONS } from './functions.generated.js';
export default { functions: FUNCTION_DEFINITIONS, categories: FUNCTION_CATEGORIES };
