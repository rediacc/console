/**
 * Parse vault content from string or object.
 * Handles JSON strings, objects, and empty/dash values.
 *
 * @param value - Vault content as string, object, or null/undefined
 * @returns Parsed object or undefined if empty/invalid
 */
export function parseVaultContent<T = Record<string, unknown>>(
  value?: string | T | null
): T | undefined {
  // Handle empty values
  if (!value || value === '-') {
    return undefined;
  }

  // If already an object, return as-is
  if (typeof value === 'object') {
    return value;
  }

  // Parse JSON string
  if (typeof value === 'string') {
    try {
      return JSON.parse(value) as T;
    } catch {
      return undefined;
    }
  }

  return undefined;
}

/**
 * Parse vault content with empty object fallback.
 * Useful when you need a guaranteed object return.
 *
 * @param value - Vault content as string, object, or null/undefined
 * @returns Parsed object or empty object if empty/invalid
 */
export function parseVaultContentOrEmpty<T = Record<string, unknown>>(
  value?: string | T | null
): T {
  // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
  return parseVaultContent(value) ?? ({} as T);
}
