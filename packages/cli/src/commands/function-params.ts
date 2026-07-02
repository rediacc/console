import {
  getValidationErrors,
  isBridgeFunction,
  safeValidateFunctionParams,
} from '@rediacc/shared/queue-vault';
import { FUNCTION_DEFINITIONS } from '@rediacc/shared/queue-vault/data/definitions';
import { t } from '../i18n/index.js';
import { ValidationError } from '../utils/errors.js';

export function parseParamOptions(paramOptions: string[] | undefined): Record<string, string> {
  const params: Record<string, string> = {};
  for (const param of paramOptions ?? []) {
    const [key, ...valueParts] = param.split('=');
    params[key] = valueParts.join('=');
  }
  return params;
}

/**
 * Coerce CLI string params to their expected types based on FUNCTION_DEFINITIONS.
 * CLI --param key=value always produces strings, but Zod schemas expect native types
 * (boolean, number). This bridges the gap using the generated type metadata.
 */
export function coerceCliParams(
  functionName: string,
  params: Record<string, string | boolean | number>
): Record<string, unknown> {
  if (!isBridgeFunction(functionName)) return params;
  const def = FUNCTION_DEFINITIONS[functionName];

  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    if (!(key in def.params)) {
      result[key] = value;
      continue;
    }
    const paramDef = def.params[key];
    switch (paramDef.type) {
      case 'bool':
        result[key] = value === true || value === 'true' || value === '1' || value === 'yes';
        break;
      case 'int':
        result[key] = typeof value === 'number' ? value : Number.parseInt(String(value), 10);
        break;
      default:
        result[key] = value;
    }
  }
  return result;
}

export function validateFunctionParams(
  functionName: string,
  params: Record<string, unknown>
): void {
  if (!isBridgeFunction(functionName)) return;
  const validationResult = safeValidateFunctionParams(functionName, params);
  if (!validationResult.success) {
    throw new ValidationError(
      t('errors.invalidFunctionParams', {
        function: functionName,
        errors: getValidationErrors(validationResult),
      })
    );
  }
}
