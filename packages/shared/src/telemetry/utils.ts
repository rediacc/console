/**
 * Platform-agnostic telemetry utilities.
 * Used by both web and CLI for consistent telemetry handling.
 */

/**
 * Sensitive keys that should be redacted from telemetry.
 * Matches any key containing these substrings (case-insensitive).
 */
const SENSITIVE_KEYS = [
  'password',
  'token',
  'key',
  'secret',
  'vault',
  'vaults',
  'vaultcontent',
  'queuevault',
  'masterpassword',
  'privatekey',
  'credential',
  'authorization',
  'cookie',
  'apikey',
] as const;

/**
 * Generate a unique session ID for telemetry attribution.
 * Format: session_{timestamp}_{random}
 */
export function generateSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
}

/**
 * Extract the API endpoint/procedure name from a URL.
 * Handles the StoredProcedure URL pattern: /api/StoredProcedure/{procedureName}
 */
export function extractApiEndpoint(url: string): string {
  try {
    const urlObj = new URL(url);
    const pathParts = urlObj.pathname.split('/').filter(Boolean);
    if (pathParts.length >= 2 && pathParts[0] === 'api' && pathParts[1] === 'StoredProcedure') {
      return pathParts[2] || 'unknown';
    }
    return pathParts.join('/') || 'unknown';
  } catch {
    // Handle relative URLs or invalid URLs
    const parts = url.split('/').filter(Boolean);
    if (parts.length >= 2 && parts[0] === 'api' && parts[1] === 'StoredProcedure') {
      return parts[2] || 'unknown';
    }
    return 'unknown';
  }
}

/**
 * Anonymize an email address by hiding the local part.
 * Example: "john.doe@example.com" -> "***@example.com"
 */
export function anonymizeEmail(email: string): string {
  const parts = email.split('@');
  if (parts.length !== 2 || !parts[1]) {
    return '[INVALID_EMAIL]';
  }
  return `***@${parts[1]}`;
}

/**
 * Check if a key name matches any sensitive key pattern.
 */
export function isSensitiveKey(key: string): boolean {
  const lowerKey = key.toLowerCase();
  return SENSITIVE_KEYS.some((sensitive) => lowerKey.includes(sensitive));
}

/**
 * Anonymize a single value based on its key and content.
 * - Sensitive keys are redacted entirely
 * - Email addresses are partially hidden
 * - Other values are returned unchanged
 */
export function anonymizeValue(key: string, value: unknown): unknown {
  // Always redact sensitive keys
  if (isSensitiveKey(key)) {
    return '[REDACTED]';
  }

  // Anonymize email addresses in string values
  if (typeof value === 'string' && value.includes('@') && value.includes('.')) {
    // Simple email pattern check
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (emailPattern.test(value)) {
      return anonymizeEmail(value);
    }
  }

  return value;
}

/**
 * Anonymize a nested object value
 */
function anonymizeNestedObject(key: string, value: object): unknown {
  if (isSensitiveKey(key)) {
    return '[REDACTED]';
  }
  return anonymizeObject(value as Record<string, unknown>);
}

/**
 * Anonymize an array value
 */
function anonymizeArrayValue(key: string, value: unknown[]): unknown {
  if (isSensitiveKey(key)) {
    return '[REDACTED]';
  }
  return value.map((item, index) => {
    if (typeof item === 'object' && item !== null) {
      return anonymizeObject(item as Record<string, unknown>);
    }
    return anonymizeValue(`${key}[${index}]`, item);
  });
}

/**
 * Recursively anonymize an object, redacting sensitive keys and emails.
 * Returns a new object with anonymized values.
 */
export function anonymizeObject(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(obj)) {
    if (value === null || value === undefined) {
      result[key] = value;
    } else if (Array.isArray(value)) {
      result[key] = anonymizeArrayValue(key, value);
    } else if (typeof value === 'object') {
      result[key] = anonymizeNestedObject(key, value);
    } else {
      result[key] = anonymizeValue(key, value);
    }
  }

  return result;
}

/** Check if arg is a value following a sensitive flag */
function isSensitiveFlagValue(arg: string, prevArg: string | undefined): boolean {
  if (!prevArg?.startsWith('-')) {
    return false;
  }
  return isSensitiveKey(prevArg.replace(/^-+/, ''));
}

/** Handle key=value pattern anonymization */
function anonymizeKeyValueArg(arg: string): string | null {
  if (!arg.includes('=')) {
    return null;
  }

  const [key, ...valueParts] = arg.split('=');
  if (key && isSensitiveKey(key)) {
    return `${key}=[REDACTED]`;
  }

  const value = valueParts.join('=');
  if (value.includes('@')) {
    return `${key}=${anonymizeEmail(value)}`;
  }

  return null;
}

/** Check if string looks like an email and anonymize it */
function anonymizeIfEmail(arg: string): string | null {
  if (!arg.includes('@') || !arg.includes('.')) {
    return null;
  }

  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (emailPattern.test(arg)) {
    return anonymizeEmail(arg);
  }

  return null;
}

/**
 * Anonymize command-line arguments array.
 * Redacts values that look like secrets or contain email addresses.
 */
export function anonymizeArgs(args: string[]): string[] {
  return args.map((arg, index) => {
    const prevArg = args[index - 1];

    if (isSensitiveFlagValue(arg, prevArg)) {
      return '[REDACTED]';
    }

    if (isSensitiveKey(arg)) {
      return '[REDACTED]';
    }

    const keyValueResult = anonymizeKeyValueArg(arg);
    if (keyValueResult !== null) {
      return keyValueResult;
    }

    const emailResult = anonymizeIfEmail(arg);
    if (emailResult !== null) {
      return emailResult;
    }

    return arg;
  });
}

/**
 * Convert an error to telemetry attributes.
 * Limits stack trace length to avoid excessive data.
 */
export function errorToAttributes(error: unknown): Record<string, string> {
  if (error instanceof Error) {
    return {
      'error.type': error.constructor.name,
      'error.message': error.message,
      'error.stack': error.stack?.slice(0, 1000) ?? '',
    };
  }
  return {
    'error.type': 'Unknown',
    'error.message': String(error),
    'error.stack': '',
  };
}

/**
 * Enrich telemetry attributes with common fields.
 */
export function enrichAttributes(
  base: Record<string, unknown>,
  context?: Record<string, unknown>
): Record<string, unknown> {
  return {
    ...base,
    'event.timestamp': Date.now(),
    ...context,
  };
}
