import { describe, expect, it } from 'vitest';
import {
  formatBoolean,
  formatPriority,
  formatRetryCount,
  formatStatus,
} from '../queueFormatters.js';

// Note: These tests verify the logic of the formatters.
// The actual output includes ANSI color codes from chalk.
// We test that the output contains the expected text content.

describe('utils/queueFormatters', () => {
  describe('formatStatus', () => {
    it('should return UNKNOWN for null', () => {
      const result = formatStatus(null);
      expect(result).toContain('UNKNOWN');
    });

    it('should return UNKNOWN for undefined', () => {
      const result = formatStatus(undefined);
      expect(result).toContain('UNKNOWN');
    });

    it('should return COMPLETED status', () => {
      const result = formatStatus('COMPLETED');
      expect(result).toContain('COMPLETED');
    });

    it('should return FAILED status', () => {
      const result = formatStatus('FAILED');
      expect(result).toContain('FAILED');
    });

    it('should return PENDING status', () => {
      const result = formatStatus('PENDING');
      expect(result).toContain('PENDING');
    });

    it('should return PROCESSING status', () => {
      const result = formatStatus('PROCESSING');
      expect(result).toContain('PROCESSING');
    });

    it('should return ASSIGNED status', () => {
      const result = formatStatus('ASSIGNED');
      expect(result).toContain('ASSIGNED');
    });

    it('should return CANCELLED status', () => {
      const result = formatStatus('CANCELLED');
      expect(result).toContain('CANCELLED');
    });

    it('should return CANCELLING status', () => {
      const result = formatStatus('CANCELLING');
      expect(result).toContain('CANCELLING');
    });

    it('should return STALE status', () => {
      const result = formatStatus('STALE');
      expect(result).toContain('STALE');
    });

    it('should handle lowercase status', () => {
      const result = formatStatus('completed');
      expect(result).toContain('completed');
    });

    it('should handle unknown status', () => {
      const result = formatStatus('CUSTOM_STATUS');
      expect(result).toContain('CUSTOM_STATUS');
    });
  });

  describe('formatPriority', () => {
    it('should return dash for undefined', () => {
      const result = formatPriority(undefined);
      expect(result).toContain('-');
    });

    it('should return dash for 0 (falsy)', () => {
      const result = formatPriority(0);
      expect(result).toContain('-');
    });

    it('should format priority 1 with Highest label', () => {
      const result = formatPriority(1);
      expect(result).toContain('P1');
      expect(result).toContain('Highest');
    });

    it('should format priority 2 with High label', () => {
      const result = formatPriority(2);
      expect(result).toContain('P2');
      expect(result).toContain('High');
    });

    it('should format priority 3 with Normal label', () => {
      const result = formatPriority(3);
      expect(result).toContain('P3');
      expect(result).toContain('Normal');
    });

    it('should format priority 4 with Low label', () => {
      const result = formatPriority(4);
      expect(result).toContain('P4');
      expect(result).toContain('Low');
    });

    it('should format priority 5 with Lowest label', () => {
      const result = formatPriority(5);
      expect(result).toContain('P5');
      expect(result).toContain('Lowest');
    });

    it('should handle out-of-range priority gracefully', () => {
      const result = formatPriority(10);
      expect(result).toContain('P10');
    });
  });

  describe('formatRetryCount', () => {
    it('should return dash for undefined', () => {
      const result = formatRetryCount(undefined);
      expect(result).toContain('-');
    });

    it('should format 0 retries', () => {
      const result = formatRetryCount(0);
      expect(result).toContain('0/');
    });

    it('should format 1 retry', () => {
      const result = formatRetryCount(1);
      expect(result).toContain('1/');
    });

    it('should format 2 retries', () => {
      const result = formatRetryCount(2);
      expect(result).toContain('2/');
    });

    it('should format max-1 retries', () => {
      // MAX_RETRY_COUNT is typically 5, so 4 should be red
      const result = formatRetryCount(4);
      expect(result).toContain('4/');
    });

    it('should format max retries', () => {
      const result = formatRetryCount(5);
      expect(result).toContain('5/');
    });
  });

  describe('formatBoolean', () => {
    it('should return dash for undefined', () => {
      const result = formatBoolean(undefined);
      expect(result).toContain('-');
    });

    it('should return checkmark for true', () => {
      const result = formatBoolean(true);
      expect(result).toContain('✓');
    });

    it('should return cross for false', () => {
      const result = formatBoolean(false);
      expect(result).toContain('✗');
    });
  });
});
