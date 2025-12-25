/**
 * Secure Context Detection Utility
 *
 * The Web Crypto API (crypto.subtle) is only available in secure contexts:
 * - HTTPS connections
 * - localhost / 127.0.0.1 (browser exception)
 * - file:// URLs
 *
 * When accessed via HTTP on non-localhost (e.g., http://192.168.178.34),
 * crypto.subtle will be undefined, causing cryptographic operations to fail.
 */

/**
 * Check if the current browsing context is secure.
 * Uses the native browser API with fallback verification.
 */
export function isSecureContext(): boolean {
  // Use native browser check if available
  if (typeof window !== 'undefined' && 'isSecureContext' in window) {
    return window.isSecureContext;
  }

  // Fallback: Check crypto.subtle availability
  return typeof crypto !== 'undefined' && typeof crypto.subtle !== 'undefined';
}

/**
 * Check if cryptographic operations are available.
 * This is more specific than isSecureContext as it directly tests crypto.subtle.
 */
export function isCryptoAvailable(): boolean {
  try {
    return (
      typeof crypto !== 'undefined' &&
      typeof crypto.subtle !== 'undefined' &&
      typeof crypto.subtle.digest === 'function'
    );
  } catch {
    return false;
  }
}

/**
 * Get information about why the context is insecure.
 * Useful for providing helpful error messages to users.
 */
export function getSecurityContextInfo(): {
  isSecure: boolean;
  protocol: string;
  hostname: string;
  isLocalhost: boolean;
  suggestion: string;
} {
  const protocol = window.location.protocol;
  const hostname = window.location.hostname;
  const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';
  const isSecure = isSecureContext();

  let suggestion = '';
  if (isSecure) {
    // Secure context, no suggestion needed
  } else if (protocol === 'http:' && !isLocalhost) {
    suggestion = `Access via HTTPS (https://${hostname}) or use localhost for development`;
  } else {
    suggestion = 'Use HTTPS or access via localhost';
  }

  return {
    isSecure,
    protocol,
    hostname,
    isLocalhost,
    suggestion,
  };
}
