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
    return btoa(value)
  } catch (error) {
    // Handle non-Latin1 characters by encoding to UTF-8 first
    if (error instanceof DOMException) {
      const utf8Bytes = new TextEncoder().encode(value)
      const binaryString = Array.from(utf8Bytes)
        .map((byte) => String.fromCharCode(byte))
        .join('')
      return btoa(binaryString)
    }
    throw error
  }
}

/**
 * Decodes a base64 string to its original value, handling UTF-8 characters
 *
 * @param value - The base64 encoded string
 * @returns Decoded string
 * @throws {DOMException} If atob is not available or decoding fails
 *
 * @example
 * decodeBase64('SGVsbG8gV29ybGQ=') // Returns: 'Hello World'
 */
export function decodeBase64(value: string): string {
  try {
    const decoded = atob(value)
    // Try to decode as UTF-8
    const bytes = Uint8Array.from(decoded, char => char.charCodeAt(0))
    return new TextDecoder().decode(bytes)
  } catch (error) {
    // Fallback to standard atob for ASCII strings
    if (error instanceof DOMException || error instanceof RangeError) {
      return atob(value)
    }
    throw error
  }
}
