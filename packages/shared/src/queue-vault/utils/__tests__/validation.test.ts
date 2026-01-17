import { describe, expect, it } from 'vitest';
import {
  formatSizeBytes,
  isValidHost,
  isValidHostname,
  isValidIP,
  // IP/Port validation (existing)
  isValidIPv4,
  isValidIPv6,
  isValidNetworkId,
  isValidPort,
  isValidSSHPrivateKey,
  // Network ID validation
  MIN_NETWORK_ID,
  NETWORK_ID_INCREMENT,
  // Size validation
  parseSize,
  validateNetworkId,
  validateSize,
  validateSizeWithMin,
  // SSH key validation
  validateSSHPrivateKey,
} from '../validation.js';

// ============================================
// Size Format Validation Tests
// ============================================

describe('parseSize', () => {
  describe('valid sizes', () => {
    it('should parse size with G suffix', () => {
      const result = parseSize('20G');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.bytes).toBe(20 * 1024 * 1024 * 1024);
      }
    });

    it('should parse size with M suffix', () => {
      const result = parseSize('500M');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.bytes).toBe(500 * 1024 * 1024);
      }
    });

    it('should parse size with T suffix', () => {
      const result = parseSize('1T');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.bytes).toBe(1024 * 1024 * 1024 * 1024);
      }
    });

    it('should parse size with K suffix', () => {
      const result = parseSize('100K');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.bytes).toBe(100 * 1024);
      }
    });

    it('should parse size with P suffix', () => {
      const result = parseSize('1P');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.bytes).toBe(1024 * 1024 * 1024 * 1024 * 1024);
      }
    });

    it('should parse lowercase suffix', () => {
      const result = parseSize('20g');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.bytes).toBe(20 * 1024 * 1024 * 1024);
      }
    });

    it('should parse decimal values', () => {
      const result = parseSize('1.5G');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.bytes).toBe(Math.floor(1.5 * 1024 * 1024 * 1024));
      }
    });

    it('should parse plain bytes (no suffix)', () => {
      const result = parseSize('1024');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.bytes).toBe(1024);
      }
    });

    it('should handle whitespace', () => {
      const result = parseSize('  20G  ');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.bytes).toBe(20 * 1024 * 1024 * 1024);
      }
    });
  });

  describe('invalid sizes', () => {
    it('should fail for empty string', () => {
      const result = parseSize('');
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error).toContain('size is required');
      }
    });

    it('should fail for whitespace only', () => {
      const result = parseSize('   ');
      expect(result.success).toBe(false);
    });

    it('should fail for invalid suffix', () => {
      const result = parseSize('20X');
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error).toContain('invalid size suffix');
      }
    });

    it('should fail for non-numeric value', () => {
      const result = parseSize('abcG');
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error).toContain('not a valid number');
      }
    });

    it('should fail for only suffix', () => {
      const result = parseSize('G');
      expect(result.success).toBe(false);
    });
  });
});

describe('validateSize', () => {
  it('should return valid with bytes for valid size', () => {
    const result = validateSize('20G');
    expect(result.valid).toBe(true);
    expect(result.bytes).toBe(20 * 1024 * 1024 * 1024);
    expect(result.error).toBeUndefined();
  });

  it('should return invalid with error for invalid size', () => {
    const result = validateSize('invalid');
    expect(result.valid).toBe(false);
    expect(result.error).toBeDefined();
    expect(result.bytes).toBeUndefined();
  });
});

describe('validateSizeWithMin', () => {
  it('should pass when size is above minimum', () => {
    const minBytes = 10 * 1024 * 1024 * 1024; // 10G
    const result = validateSizeWithMin('20G', minBytes);
    expect(result.valid).toBe(true);
    expect(result.bytes).toBe(20 * 1024 * 1024 * 1024);
  });

  it('should fail when size is below minimum', () => {
    const minBytes = 50 * 1024 * 1024 * 1024; // 50G
    const result = validateSizeWithMin('20G', minBytes);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('below minimum');
  });

  it('should pass when size equals minimum', () => {
    const minBytes = 20 * 1024 * 1024 * 1024; // 20G
    const result = validateSizeWithMin('20G', minBytes);
    expect(result.valid).toBe(true);
  });
});

describe('formatSizeBytes', () => {
  it('should format bytes to G', () => {
    expect(formatSizeBytes(20 * 1024 * 1024 * 1024)).toBe('20G');
  });

  it('should format bytes to M', () => {
    expect(formatSizeBytes(500 * 1024 * 1024)).toBe('500M');
  });

  it('should format bytes to T', () => {
    expect(formatSizeBytes(1024 * 1024 * 1024 * 1024)).toBe('1T');
  });

  it('should format bytes to K', () => {
    expect(formatSizeBytes(100 * 1024)).toBe('100K');
  });

  it('should return 0 for zero bytes', () => {
    expect(formatSizeBytes(0)).toBe('0');
  });

  it('should format non-round values with decimal', () => {
    expect(formatSizeBytes(1536 * 1024 * 1024)).toBe('1.5G');
  });

  it('should return plain bytes for small values', () => {
    expect(formatSizeBytes(500)).toBe('500');
  });
});

// ============================================
// Network ID Validation Tests
// ============================================

describe('validateNetworkId', () => {
  describe('valid network IDs', () => {
    it('should accept minimum network ID (2816)', () => {
      const result = validateNetworkId(2816);
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it('should accept 2816 + 64 = 2880', () => {
      const result = validateNetworkId(2880);
      expect(result.valid).toBe(true);
    });

    it('should accept 2816 + 128 = 2944', () => {
      const result = validateNetworkId(2944);
      expect(result.valid).toBe(true);
    });

    it('should accept 2816 + 256 = 3072', () => {
      const result = validateNetworkId(3072);
      expect(result.valid).toBe(true);
    });

    it('should accept large valid network ID', () => {
      const result = validateNetworkId(2816 + 64 * 100);
      expect(result.valid).toBe(true);
    });
  });

  describe('invalid network IDs', () => {
    it('should reject ID below minimum', () => {
      const result = validateNetworkId(2800);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('must be >= 2816');
    });

    it('should reject zero', () => {
      const result = validateNetworkId(0);
      expect(result.valid).toBe(false);
    });

    it('should reject negative numbers', () => {
      const result = validateNetworkId(-100);
      expect(result.valid).toBe(false);
    });

    it('should reject ID not following 64 increment pattern', () => {
      const result = validateNetworkId(2817);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('must be 2816 + (n * 64)');
    });

    it('should reject 2816 + 32 (not multiple of 64)', () => {
      const result = validateNetworkId(2848);
      expect(result.valid).toBe(false);
    });

    it('should reject NaN', () => {
      const result = validateNetworkId(Number.NaN);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('must be a number');
    });

    it('should reject non-integer', () => {
      const result = validateNetworkId(2816.5);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('must be an integer');
    });
  });

  describe('constants', () => {
    it('should export MIN_NETWORK_ID as 2816', () => {
      expect(MIN_NETWORK_ID).toBe(2816);
    });

    it('should export NETWORK_ID_INCREMENT as 64', () => {
      expect(NETWORK_ID_INCREMENT).toBe(64);
    });
  });
});

describe('isValidNetworkId', () => {
  it('should return true for valid network ID', () => {
    expect(isValidNetworkId(2816)).toBe(true);
    expect(isValidNetworkId(2880)).toBe(true);
  });

  it('should return false for invalid network ID', () => {
    expect(isValidNetworkId(2817)).toBe(false);
    expect(isValidNetworkId(100)).toBe(false);
  });
});

// ============================================
// SSH Private Key Validation Tests
// ============================================

describe('validateSSHPrivateKey', () => {
  const VALID_OPENSSH_KEY = `-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBIvGPp0Ew8rYT7eBmV8xTkSzgz8IY1qJKf5Fm5HqRc9wAAAJi5Ywl+uWMJ
fgAAAAtzc2gtZWQyNTUxOQAAACBIvGPp0Ew8rYT7eBmV8xTkSzgz8IY1qJKf5Fm5HqRc9w
AAAED0xJR5yC9VlFN5nJ9w9Y5V5QkXlS5V5V5V5V5V5V5V5ki8Y+nQTDythPt4GZXzFORL
ODPwhjWokp/kWbkepFz3AAAADXRlc3RAZXhhbXBsZQECAwQFBg==
-----END OPENSSH PRIVATE KEY-----`;

  const VALID_RSA_KEY = `-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB1pvCypvQniWrM6epQ
7V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V5V
-----END RSA PRIVATE KEY-----`;

  const VALID_EC_KEY = `-----BEGIN EC PRIVATE KEY-----
MHQCAQEEICVcMCHmpmXZ0xgCfY5V5V5V5V5V5V5V5V5V5V5V5V5VoAcGBSuBBAAK
oUQDQgAEtest
-----END EC PRIVATE KEY-----`;

  describe('valid keys', () => {
    it('should accept valid OpenSSH private key', () => {
      const result = validateSSHPrivateKey(VALID_OPENSSH_KEY);
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it('should accept valid RSA private key', () => {
      const result = validateSSHPrivateKey(VALID_RSA_KEY);
      expect(result.valid).toBe(true);
    });

    it('should accept valid EC private key', () => {
      const result = validateSSHPrivateKey(VALID_EC_KEY);
      expect(result.valid).toBe(true);
    });

    it('should accept key with leading/trailing whitespace', () => {
      const result = validateSSHPrivateKey(`  ${VALID_OPENSSH_KEY}  `);
      expect(result.valid).toBe(true);
    });

    it('should accept generic PRIVATE KEY format', () => {
      const key = `-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgtest
-----END PRIVATE KEY-----`;
      const result = validateSSHPrivateKey(key);
      expect(result.valid).toBe(true);
    });

    it('should accept encrypted private key format', () => {
      const key = `-----BEGIN ENCRYPTED PRIVATE KEY-----
MIIFHDBOBgtest
-----END ENCRYPTED PRIVATE KEY-----`;
      const result = validateSSHPrivateKey(key);
      expect(result.valid).toBe(true);
    });
  });

  describe('invalid keys', () => {
    it('should reject empty string', () => {
      const result = validateSSHPrivateKey('');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('is required');
    });

    it('should reject whitespace only', () => {
      const result = validateSSHPrivateKey('   ');
      expect(result.valid).toBe(false);
    });

    it('should reject null', () => {
      const result = validateSSHPrivateKey(null as unknown as string);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('is required');
    });

    it('should reject undefined', () => {
      const result = validateSSHPrivateKey(undefined as unknown as string);
      expect(result.valid).toBe(false);
    });

    it('should reject plain text', () => {
      const result = validateSSHPrivateKey('not a key');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('PEM format');
    });

    it('should reject base64-encoded key', () => {
      const encoded = btoa(VALID_OPENSSH_KEY);
      const result = validateSSHPrivateKey(encoded);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('PEM format');
    });

    it('should reject public key format', () => {
      const publicKey = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgtest
-----END PUBLIC KEY-----`;
      const result = validateSSHPrivateKey(publicKey);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('must be in PEM format');
    });

    it('should reject key without END marker', () => {
      const incomplete = `-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmU=`;
      const result = validateSSHPrivateKey(incomplete);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('missing END marker');
    });

    it('should reject certificate format', () => {
      const cert = `-----BEGIN CERTIFICATE-----
MIIBkTCB+wIJAtest
-----END CERTIFICATE-----`;
      const result = validateSSHPrivateKey(cert);
      expect(result.valid).toBe(false);
    });
  });
});

describe('isValidSSHPrivateKey', () => {
  it('should return true for valid key', () => {
    const key = `-----BEGIN OPENSSH PRIVATE KEY-----
test
-----END OPENSSH PRIVATE KEY-----`;
    expect(isValidSSHPrivateKey(key)).toBe(true);
  });

  it('should return false for invalid key', () => {
    expect(isValidSSHPrivateKey('not a key')).toBe(false);
    expect(isValidSSHPrivateKey('')).toBe(false);
  });
});

// ============================================
// IP/Port Validation Tests (existing functions)
// ============================================

describe('isValidIPv4', () => {
  it('should accept valid IPv4 addresses', () => {
    expect(isValidIPv4('192.168.1.1')).toBe(true);
    expect(isValidIPv4('10.0.0.1')).toBe(true);
    expect(isValidIPv4('255.255.255.255')).toBe(true);
    expect(isValidIPv4('0.0.0.0')).toBe(true);
  });

  it('should reject invalid IPv4 addresses', () => {
    expect(isValidIPv4('256.1.1.1')).toBe(false);
    expect(isValidIPv4('192.168.1')).toBe(false);
    expect(isValidIPv4('192.168.1.1.1')).toBe(false);
    expect(isValidIPv4('abc.def.ghi.jkl')).toBe(false);
    expect(isValidIPv4('')).toBe(false);
  });
});

describe('isValidIPv6', () => {
  it('should accept valid IPv6 addresses', () => {
    expect(isValidIPv6('2001:0db8:85a3:0000:0000:8a2e:0370:7334')).toBe(true);
    expect(isValidIPv6('::1')).toBe(true);
    expect(isValidIPv6('::')).toBe(true);
  });

  it('should reject invalid IPv6 addresses', () => {
    expect(isValidIPv6('192.168.1.1')).toBe(false);
    expect(isValidIPv6('not-an-ip')).toBe(false);
    expect(isValidIPv6('')).toBe(false);
  });
});

describe('isValidIP', () => {
  it('should accept both IPv4 and IPv6', () => {
    expect(isValidIP('192.168.1.1')).toBe(true);
    expect(isValidIP('::1')).toBe(true);
  });

  it('should reject invalid IPs', () => {
    expect(isValidIP('not-an-ip')).toBe(false);
  });
});

describe('isValidHostname', () => {
  it('should accept valid hostnames', () => {
    expect(isValidHostname('example.com')).toBe(true);
    expect(isValidHostname('sub.example.com')).toBe(true);
    expect(isValidHostname('localhost')).toBe(true);
    expect(isValidHostname('server-01')).toBe(true);
  });

  it('should reject invalid hostnames', () => {
    expect(isValidHostname('-invalid')).toBe(false);
    expect(isValidHostname('invalid-')).toBe(false);
    expect(isValidHostname('')).toBe(false);
    expect(isValidHostname('a'.repeat(254))).toBe(false); // Too long
  });
});

describe('isValidHost', () => {
  it('should accept IP addresses and hostnames', () => {
    expect(isValidHost('192.168.1.1')).toBe(true);
    expect(isValidHost('example.com')).toBe(true);
    expect(isValidHost('::1')).toBe(true);
  });
});

describe('isValidPort', () => {
  it('should accept valid ports', () => {
    expect(isValidPort(22)).toBe(true);
    expect(isValidPort(80)).toBe(true);
    expect(isValidPort(443)).toBe(true);
    expect(isValidPort(65535)).toBe(true);
    expect(isValidPort(1)).toBe(true);
    expect(isValidPort('22')).toBe(true);
  });

  it('should accept undefined/null (port is optional)', () => {
    expect(isValidPort(undefined)).toBe(true);
    expect(isValidPort(null)).toBe(true);
  });

  it('should reject invalid ports', () => {
    expect(isValidPort(0)).toBe(false);
    expect(isValidPort(-1)).toBe(false);
    expect(isValidPort(65536)).toBe(false);
    expect(isValidPort(1.5)).toBe(false);
    expect(isValidPort('abc')).toBe(false);
  });
});
