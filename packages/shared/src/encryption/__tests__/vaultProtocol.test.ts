import { describe, it, expect } from 'vitest';
import { isEncrypted, analyzeVaultProtocolState, VaultProtocolState } from '../vaultProtocol.js';

describe('vaultProtocol', () => {
  describe('isEncrypted', () => {
    it('should return true for valid encrypted string (base64, long enough)', () => {
      // Base64 string >= 40 chars that's not valid JSON
      const encrypted = 'YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY3ODkw';
      expect(isEncrypted(encrypted)).toBe(true);
    });

    it('should return true for typical encrypted output format', () => {
      // Realistic encrypted output: salt(16) + iv(12) + data + tag(16) encoded as base64
      const realistic =
        'dGhpcyBpcyBhIHNhbHQxMjNpdmRhdGExMjM0NTZ0aGlzIGlzIGEgdGFnMTIzNDU2Nzg5MDEyMzQ1Njc4OQ==';
      expect(isEncrypted(realistic)).toBe(true);
    });

    it('should return false for plain JSON object', () => {
      expect(isEncrypted('{"key": "value"}')).toBe(false);
    });

    it('should return false for plain JSON array', () => {
      expect(isEncrypted('[1, 2, 3]')).toBe(false);
    });

    it('should return false for short strings', () => {
      expect(isEncrypted('short')).toBe(false);
      expect(isEncrypted('abc123')).toBe(false);
    });

    it('should return false for strings less than 20 chars', () => {
      expect(isEncrypted('1234567890123456789')).toBe(false); // 19 chars
    });

    it('should return false for strings less than 40 chars even if base64', () => {
      // Valid base64 but less than 40 chars
      expect(isEncrypted('YWJjZGVmZ2hpamtsbW5vcHFyc3R1')).toBe(false); // 28 chars
    });

    it('should return false for null', () => {
      expect(isEncrypted(null)).toBe(false);
    });

    it('should return false for undefined', () => {
      expect(isEncrypted(undefined)).toBe(false);
    });

    it('should return false for empty string', () => {
      expect(isEncrypted('')).toBe(false);
    });

    it('should return false for non-base64 characters', () => {
      // Contains invalid base64 chars like !@#
      const invalid = 'abc!@#defghijklmnopqrstuvwxyz1234567890!@#';
      expect(isEncrypted(invalid)).toBe(false);
    });
  });

  describe('VaultProtocolState enum', () => {
    it('should have all expected states', () => {
      expect(VaultProtocolState.NOT_ENABLED).toBe('NOT_ENABLED');
      expect(VaultProtocolState.PASSWORD_REQUIRED).toBe('PASSWORD_REQUIRED');
      expect(VaultProtocolState.INVALID_PASSWORD).toBe('INVALID_PASSWORD');
      expect(VaultProtocolState.VALID).toBe('VALID');
      expect(VaultProtocolState.PASSWORD_NOT_NEEDED).toBe('PASSWORD_NOT_NEEDED');
    });
  });

  describe('analyzeVaultProtocolState', () => {
    const encryptedVault =
      'YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA=';
    const plainVault = '{"SSH_KEY": "secret"}';

    describe('when company has no encryption', () => {
      it('should return NOT_ENABLED when no password provided', () => {
        expect(analyzeVaultProtocolState(plainVault, false)).toBe(VaultProtocolState.NOT_ENABLED);
        expect(analyzeVaultProtocolState(null, false)).toBe(VaultProtocolState.NOT_ENABLED);
        expect(analyzeVaultProtocolState(undefined, false)).toBe(VaultProtocolState.NOT_ENABLED);
      });

      it('should return PASSWORD_NOT_NEEDED when password provided but not needed', () => {
        expect(analyzeVaultProtocolState(plainVault, true)).toBe(
          VaultProtocolState.PASSWORD_NOT_NEEDED
        );
        expect(analyzeVaultProtocolState(null, true)).toBe(VaultProtocolState.PASSWORD_NOT_NEEDED);
      });
    });

    describe('when company has encryption', () => {
      it('should return PASSWORD_REQUIRED when no password provided', () => {
        expect(analyzeVaultProtocolState(encryptedVault, false)).toBe(
          VaultProtocolState.PASSWORD_REQUIRED
        );
      });

      it('should return INVALID_PASSWORD when password is invalid', () => {
        expect(analyzeVaultProtocolState(encryptedVault, true, false)).toBe(
          VaultProtocolState.INVALID_PASSWORD
        );
      });

      it('should return VALID when password is valid', () => {
        expect(analyzeVaultProtocolState(encryptedVault, true, true)).toBe(VaultProtocolState.VALID);
      });
    });
  });
});
