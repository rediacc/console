/**
 * Encoding utilities for base64 and other encoding operations
 */

/**
 * Encodes a string to base64, handling UTF-8 characters properly
 *
 * This function handles the common issue where btoa() fails with non-Latin1 characters
 * by encoding to UTF-8 bytes first before converting to base64.
 *
 * @param value - The string to encode
 * @returns Base64 encoded string
 * @throws {DOMException} If btoa is not available or encoding fails
 *
 * @example
 * encodeBase64('Hello World') // Returns: 'SGVsbG8gV29ybGQ='
 * encodeBase64('Hello 世界')  // Returns: base64 encoded UTF-8 string
 */
export function encodeBase64(value: string): string {
  try {
    // Try standard btoa for ASCII/Latin1 strings
    return btoa(value);
  } catch (error) {
    // Handle non-Latin1 characters by encoding to UTF-8 first
    if (error instanceof DOMException) {
      const utf8Bytes = new TextEncoder().encode(value);
      const binaryString = Array.from(utf8Bytes)
        .map((byte) => String.fromCharCode(byte))
        .join('');
      return btoa(binaryString);
    }
    throw error;
  }
}
