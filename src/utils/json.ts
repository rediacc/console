/**
 * Minifies a JSON string by removing unnecessary whitespace
 * @param json - The JSON string to minify
 * @returns Minified JSON string
 */
export function minifyJSON(json: string): string {
  try {
    // Parse and re-stringify to remove all unnecessary whitespace
    const parsed = JSON.parse(json);
    return JSON.stringify(parsed);
  } catch (error) {
    // If parsing fails, return the original string
    console.error('Failed to minify JSON:', error);
    return json;
  }
}

/**
 * Minifies a JSON object by converting to string without whitespace
 * @param obj - The object to convert to minified JSON
 * @returns Minified JSON string
 */
export function objectToMinifiedJSON(obj: any): string {
  try {
    return JSON.stringify(obj);
  } catch (error) {
    console.error('Failed to convert object to minified JSON:', error);
    return '{}';
  }
}

/**
 * Pretty prints a JSON string with proper indentation
 * @param json - The JSON string to format
 * @param indent - Number of spaces for indentation (default: 2)
 * @returns Formatted JSON string
 */
export function prettifyJSON(json: string, indent: number = 2): string {
  try {
    const parsed = JSON.parse(json);
    return JSON.stringify(parsed, null, indent);
  } catch (error) {
    console.error('Failed to prettify JSON:', error);
    return json;
  }
}