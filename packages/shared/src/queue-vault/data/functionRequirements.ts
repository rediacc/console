import functionsData from './functions.json'
import type { FunctionRequirements } from '../types/requirements'

export const FUNCTION_REQUIREMENTS: Record<string, { requirements: FunctionRequirements }> =
  functionsData.functions as Record<string, { requirements: FunctionRequirements }>
