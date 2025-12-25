import { describe, expect, it } from 'vitest';
import {
  formatStatus,
  formatPriority,
  formatBoolean,
  formatRetryCount,
  formatError,
} from '../utils/queueFormatters.js';

describe('Queue Formatters', () => {
  describe('formatStatus', () => {
    it('should format COMPLETED status in green', () => {
      const result = formatStatus('COMPLETED');
      expect(result).toContain('COMPLETED');
    });

    it('should format FAILED status in red', () => {
      const result = formatStatus('FAILED');
      expect(result).toContain('FAILED');
    });

    it('should format PENDING status', () => {
      const result = formatStatus('PENDING');
      expect(result).toContain('PENDING');
    });

    it('should format PROCESSING status', () => {
      const result = formatStatus('PROCESSING');
      expect(result).toContain('PROCESSING');
    });

    it('should handle undefined status', () => {
      const result = formatStatus(undefined);
      expect(result).toContain('UNKNOWN');
    });

    it('should handle case-insensitive status', () => {
      const result = formatStatus('completed');
      expect(result).toContain('completed');
    });
  });

  describe('formatPriority', () => {
    it('should format priority 1 as highest', () => {
      const result = formatPriority(1);
      expect(result).toContain('P1');
      expect(result).toContain('Highest');
    });

    it('should format priority 3 as normal', () => {
      const result = formatPriority(3);
      expect(result).toContain('P3');
      expect(result).toContain('Normal');
    });

    it('should format priority 5 as lowest', () => {
      const result = formatPriority(5);
      expect(result).toContain('P5');
      expect(result).toContain('Lowest');
    });

    it('should handle undefined priority', () => {
      const result = formatPriority(undefined);
      expect(result).toContain('-');
    });
  });

  describe('formatBoolean', () => {
    it('should format true as checkmark', () => {
      const result = formatBoolean(true);
      expect(result).toContain('✓');
    });

    it('should format false as cross', () => {
      const result = formatBoolean(false);
      expect(result).toContain('✗');
    });

    it('should handle undefined as dash', () => {
      const result = formatBoolean(undefined);
      expect(result).toContain('-');
    });
  });

  describe('formatRetryCount', () => {
    it('should format 0 retries in green', () => {
      const result = formatRetryCount(0);
      expect(result).toContain('0/');
    });

    it('should format 1 retry in yellow', () => {
      const result = formatRetryCount(1);
      expect(result).toContain('1/');
    });

    it('should handle undefined retry count', () => {
      const result = formatRetryCount(undefined);
      expect(result).toContain('-');
    });
  });

  describe('formatError', () => {
    it('should format error with severity badge', () => {
      const result = formatError('ERROR: Something went wrong');
      expect(result).toContain('ERROR');
    });

    it('should handle undefined error', () => {
      const result = formatError(undefined);
      expect(result).toContain('No errors');
    });

    it('should handle plain text without severity prefix', () => {
      const result = formatError('Something went wrong');
      // Plain text gets [UNKNOWN] badge
      expect(result).toContain('Something went wrong');
    });

    it('should show count for multiple errors', () => {
      const result = formatError('ERROR: First\nWARNING: Second');
      expect(result).toContain('+1 more');
    });

    it('should show all errors when showAll is true', () => {
      const result = formatError('ERROR: First\nWARNING: Second', true);
      expect(result).toContain('ERROR');
      expect(result).toContain('WARNING');
    });
  });
});
