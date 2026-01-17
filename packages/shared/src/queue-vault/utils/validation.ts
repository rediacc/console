export function isBase64(value: string): boolean {
  const base64Pattern = /^[A-Za-z0-9+/]*={0,2}$/;
  const valueWithoutWhitespace = value.replaceAll(/\s/g, '');
  return base64Pattern.test(valueWithoutWhitespace) && valueWithoutWhitespace.length % 4 === 0;
}

export function getParamArray(params: Record<string, unknown>, key: string): string[] {
  const value = params[key];
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string');
  }
  if (typeof value === 'string' && value.length > 0) {
    return [value];
  }
  return [];
}

export function getParamValue(params: Record<string, unknown>, key: string): string | undefined {
  const value = params[key];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

// ============================================
// IP/Port Validation Utilities
// ============================================

/**
 * Validate IPv4 address format.
 * @param ip - The IP address string to validate
 * @returns true if valid IPv4 address
 */
export function isValidIPv4(ip: string): boolean {
  if (!ip || typeof ip !== 'string') return false;
  const ipv4Pattern =
    /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$/;
  return ipv4Pattern.test(ip);
}

/**
 * Validate IPv6 address format.
 * @param ip - The IP address string to validate
 * @returns true if valid IPv6 address
 */
export function isValidIPv6(ip: string): boolean {
  if (!ip || typeof ip !== 'string') return false;
  // Simplified IPv6 pattern - covers most common formats including compressed
  const ipv6Pattern =
    /^(?:(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|(?:[0-9a-fA-F]{1,4}:){1,7}:|(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}|(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}|(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}|(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}|:(?::[0-9a-fA-F]{1,4}){1,7}|::)$/;
  return ipv6Pattern.test(ip);
}

/**
 * Validate IP address (IPv4 or IPv6).
 * @param ip - The IP address string to validate
 * @returns true if valid IPv4 or IPv6 address
 */
export function isValidIP(ip: string): boolean {
  return isValidIPv4(ip) || isValidIPv6(ip);
}

/**
 * Validate hostname format (RFC 1123).
 * @param hostname - The hostname string to validate
 * @returns true if valid hostname
 */
export function isValidHostname(hostname: string): boolean {
  if (!hostname || typeof hostname !== 'string') return false;
  if (hostname.length > 253) return false;

  // Hostname pattern: labels separated by dots, each label 1-63 chars
  const hostnamePattern = /^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(?:\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))*$/;
  return hostnamePattern.test(hostname);
}

/**
 * Validate host (IP address or hostname).
 * @param host - The host string to validate
 * @returns true if valid IP address or hostname
 */
export function isValidHost(host: string): boolean {
  return isValidIP(host) || isValidHostname(host);
}

/**
 * Validate port number.
 * @param port - The port number to validate
 * @returns true if port is between 1 and 65535
 */
export function isValidPort(port: number | string | undefined | null): boolean {
  if (port === undefined || port === null) return true; // Port is optional
  const portNum = typeof port === 'string' ? Number.parseInt(port, 10) : port;
  return !Number.isNaN(portNum) && Number.isInteger(portNum) && portNum >= 1 && portNum <= 65535;
}

/**
 * Validate SSH connection details.
 * @param ip - IP address or hostname
 * @param port - Port number (optional, defaults to 22)
 * @param user - Username (optional)
 * @returns Validation result with errors array
 */
export function validateSSHConnection(
  ip: string,
  port?: number | string,
  user?: string
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!ip) {
    errors.push('IP address or hostname is required');
  } else if (!isValidHost(ip)) {
    errors.push(`Invalid IP address or hostname: ${ip}`);
  }

  if (port !== undefined && !isValidPort(port)) {
    errors.push(`Invalid port number: ${port} (must be 1-65535)`);
  }

  if (user?.length === 0) {
    errors.push('Username cannot be empty if provided');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Validate machine vault connection details.
 * @param vault - Machine vault content
 * @returns Validation result with errors array
 */
export function validateMachineVault(vault: Record<string, unknown>): {
  valid: boolean;
  errors: string[];
} {
  const ip = String(vault['ip'] ?? vault['IP'] ?? '');
  const port = vault['port'] ?? vault['PORT'];
  const user = vault['user'] ?? vault['USER'];

  return validateSSHConnection(ip, port as number | string | undefined, user as string | undefined);
}

// ============================================
// Size Format Validation
// ============================================

/** Size unit multipliers (IEC binary units) */
const SIZE_MULTIPLIERS: Record<string, number> = {
  K: 1024,
  M: 1024 * 1024,
  G: 1024 * 1024 * 1024,
  T: 1024 * 1024 * 1024 * 1024,
  P: 1024 * 1024 * 1024 * 1024 * 1024,
};

/**
 * Parse a size string (e.g., "20G", "500M", "1T") into bytes.
 * Matches renet's ParseSize function exactly.
 *
 * @param size - Size string with optional suffix (K, M, G, T, P)
 * @returns Parsed bytes or error
 *
 * @example
 * parseSize("20G")   // { success: true, bytes: 21474836480 }
 * parseSize("500M")  // { success: true, bytes: 524288000 }
 * parseSize("1T")    // { success: true, bytes: 1099511627776 }
 * parseSize("1024")  // { success: true, bytes: 1024 }
 * parseSize("")      // { success: false, error: "size is required..." }
 * parseSize("20X")   // { success: false, error: "invalid size suffix..." }
 */
export function parseSize(
  size: string
): { success: true; bytes: number } | { success: false; error: string } {
  const trimmed = size.trim();

  if (!trimmed) {
    return { success: false, error: 'size is required (e.g., 20G, 500M, 1T)' };
  }

  const lastChar = trimmed[trimmed.length - 1];

  // Check if last character is a letter (suffix)
  if (/[a-zA-Z]/.test(lastChar)) {
    const numStr = trimmed.slice(0, -1);
    const suffix = lastChar.toUpperCase();

    const num = Number.parseFloat(numStr);
    if (Number.isNaN(num)) {
      return {
        success: false,
        error: `invalid size format "${size}": numeric part is not a valid number`,
      };
    }

    const multiplier = SIZE_MULTIPLIERS[suffix];
    if (!multiplier) {
      return { success: false, error: `invalid size suffix "${lastChar}": use K, M, G, T, or P` };
    }

    return { success: true, bytes: Math.floor(num * multiplier) };
  }

  // No suffix - parse as bytes
  const bytes = Number.parseInt(trimmed, 10);
  if (Number.isNaN(bytes)) {
    return { success: false, error: `invalid size format "${size}": not a valid number` };
  }

  return { success: true, bytes };
}

/**
 * Validate a size string format.
 * @param size - Size string to validate (e.g., "20G", "500M", "1T")
 * @returns Validation result
 */
export function validateSize(size: string): { valid: boolean; error?: string; bytes?: number } {
  const result = parseSize(size);
  if (result.success) {
    return { valid: true, bytes: result.bytes };
  }
  return { valid: false, error: result.error };
}

/**
 * Validate size with minimum bytes requirement.
 * @param size - Size string to validate
 * @param minBytes - Minimum required bytes
 * @returns Validation result
 */
export function validateSizeWithMin(
  size: string,
  minBytes: number
): { valid: boolean; error?: string; bytes?: number } {
  const result = parseSize(size);
  if (!result.success) {
    return { valid: false, error: result.error };
  }

  if (result.bytes < minBytes) {
    return {
      valid: false,
      error: `size ${size} is below minimum ${formatSizeBytes(minBytes)}`,
    };
  }

  return { valid: true, bytes: result.bytes };
}

/**
 * Format bytes as human-readable size string.
 * @param bytes - Number of bytes
 * @returns Formatted string (e.g., "20G", "512M")
 */
export function formatSizeBytes(bytes: number): string {
  if (bytes === 0) return '0';

  const units = [
    { suffix: 'P', size: SIZE_MULTIPLIERS.P },
    { suffix: 'T', size: SIZE_MULTIPLIERS.T },
    { suffix: 'G', size: SIZE_MULTIPLIERS.G },
    { suffix: 'M', size: SIZE_MULTIPLIERS.M },
    { suffix: 'K', size: SIZE_MULTIPLIERS.K },
  ];

  for (const { suffix, size } of units) {
    if (bytes >= size) {
      const val = bytes / size;
      if (val === Math.floor(val)) {
        return `${Math.floor(val)}${suffix}`;
      }
      return `${val.toFixed(1)}${suffix}`;
    }
  }

  return String(bytes);
}

// ============================================
// Network ID Validation
// ============================================

/** Minimum valid network ID (matches renet) */
export const MIN_NETWORK_ID = 2816;

/** Required increment between network IDs (matches renet) */
export const NETWORK_ID_INCREMENT = 64;

/**
 * Validate a network ID.
 * Network IDs must be >= 2816 and follow the pattern 2816 + (n * 64).
 * Matches renet's ValidateNetworkID function exactly.
 *
 * @param networkId - The network ID to validate
 * @returns Validation result
 *
 * @example
 * validateNetworkId(2816)  // { valid: true }
 * validateNetworkId(2880)  // { valid: true } (2816 + 64)
 * validateNetworkId(3072)  // { valid: true } (2816 + 256)
 * validateNetworkId(2800)  // { valid: false, error: "must be >= 2816" }
 * validateNetworkId(2817)  // { valid: false, error: "must be 2816 + (n * 64)" }
 */
export function validateNetworkId(networkId: number): { valid: boolean; error?: string } {
  if (typeof networkId !== 'number' || Number.isNaN(networkId)) {
    return { valid: false, error: 'network ID must be a number' };
  }

  if (!Number.isInteger(networkId)) {
    return { valid: false, error: 'network ID must be an integer' };
  }

  if (networkId < MIN_NETWORK_ID) {
    return { valid: false, error: `invalid network ID: must be >= ${MIN_NETWORK_ID}` };
  }

  if ((networkId - MIN_NETWORK_ID) % NETWORK_ID_INCREMENT !== 0) {
    return {
      valid: false,
      error: `invalid network ID: must be ${MIN_NETWORK_ID} + (n * ${NETWORK_ID_INCREMENT})`,
    };
  }

  return { valid: true };
}

/**
 * Check if a network ID is valid.
 * @param networkId - The network ID to check
 * @returns true if valid
 */
export function isValidNetworkId(networkId: number): boolean {
  return validateNetworkId(networkId).valid;
}

// ============================================
// SSH Key Format Validation
// ============================================

/** Common SSH private key PEM headers */
const SSH_PRIVATE_KEY_HEADERS = [
  '-----BEGIN OPENSSH PRIVATE KEY-----',
  '-----BEGIN RSA PRIVATE KEY-----',
  '-----BEGIN DSA PRIVATE KEY-----',
  '-----BEGIN EC PRIVATE KEY-----',
  '-----BEGIN PRIVATE KEY-----',
  '-----BEGIN ENCRYPTED PRIVATE KEY-----',
] as const;

/**
 * Validate SSH private key format.
 * Accepts PEM (plain text).
 * This provides early validation before the key reaches renet.
 *
 * @param key - The SSH private key (plain text PEM)
 * @returns Validation result
 *
 * @example
 * validateSSHPrivateKey("-----BEGIN OPENSSH PRIVATE KEY-----\n...")  // { valid: true }
 * validateSSHPrivateKey("not a key")  // { valid: false, error: "..." }
 */
export function validateSSHPrivateKey(key: string): { valid: boolean; error?: string } {
  if (!key || typeof key !== 'string') {
    return { valid: false, error: 'SSH private key is required' };
  }

  const trimmed = key.trim();
  if (!trimmed) {
    return { valid: false, error: 'SSH private key cannot be empty' };
  }

  if (!trimmed.startsWith('-----')) {
    return {
      valid: false,
      error:
        'SSH private key must be in PEM format (should start with -----BEGIN ... PRIVATE KEY-----)',
    };
  }

  const keyContent = trimmed;

  // Check for valid PEM header
  const hasValidHeader = SSH_PRIVATE_KEY_HEADERS.some((header) =>
    keyContent.trim().startsWith(header)
  );

  if (!hasValidHeader) {
    return {
      valid: false,
      error:
        'SSH private key must be in PEM format (should start with -----BEGIN ... PRIVATE KEY-----)',
    };
  }

  // Check for END marker
  if (!keyContent.includes('-----END') || !keyContent.includes('PRIVATE KEY-----')) {
    return {
      valid: false,
      error: 'SSH private key PEM format is incomplete (missing END marker)',
    };
  }

  return { valid: true };
}

/**
 * Check if an SSH private key format is valid.
 * @param key - The SSH private key to check
 * @returns true if valid format
 */
export function isValidSSHPrivateKey(key: string): boolean {
  return validateSSHPrivateKey(key).valid;
}
