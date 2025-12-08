/**
 * Shared validation utilities
 */

/**
 * Validate GUID/UUID format
 * @param value - String to validate
 * @returns True if the string is a valid GUID
 */
export function isValidGuid(value: string): boolean {
  const guidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return guidRegex.test(value);
}

/**
 * Validate JSON string
 * @param jsonString - String to validate as JSON
 * @returns True if the string is valid JSON
 */
export function isValidJson(jsonString: string): boolean {
  try {
    JSON.parse(jsonString);
    return true;
  } catch {
    return false;
  }
}
