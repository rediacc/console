import { describe, expect, it } from 'vitest';
import { STALE_TASK_CONSTANTS } from '@rediacc/shared/queue';
import { isTaskInTerminalState } from './taskStateUtils';

describe('taskStateUtils', () => {
  describe('isTaskInTerminalState', () => {
    it('should return true for COMPLETED status', () => {
      const queueDetails = { status: 'COMPLETED' };
      expect(isTaskInTerminalState(queueDetails)).toBe(true);
    });

    it('should return true for CANCELLED status', () => {
      const queueDetails = { status: 'CANCELLED' };
      expect(isTaskInTerminalState(queueDetails)).toBe(true);
    });

    it('should return true for FAILED status with permanentlyFailed flag', () => {
      const queueDetails = {
        status: 'FAILED',
        permanentlyFailed: true,
        retryCount: 1,
      };
      expect(isTaskInTerminalState(queueDetails)).toBe(true);
    });

    it('should return true for FAILED status with max retries reached', () => {
      const queueDetails = {
        status: 'FAILED',
        retryCount: STALE_TASK_CONSTANTS.MAX_RETRY_COUNT,
        permanentlyFailed: false,
      };
      expect(isTaskInTerminalState(queueDetails)).toBe(true);
    });

    it('should return true for PENDING status with max retries and failure reason', () => {
      const queueDetails = {
        status: 'PENDING',
        retryCount: STALE_TASK_CONSTANTS.MAX_RETRY_COUNT,
        lastFailureReason: 'Connection timeout',
      };
      expect(isTaskInTerminalState(queueDetails)).toBe(true);
    });

    it('should return false for PROCESSING status', () => {
      const queueDetails = { status: 'PROCESSING', retryCount: 0 };
      expect(isTaskInTerminalState(queueDetails)).toBe(false);
    });

    it('should return false for ASSIGNED status', () => {
      const queueDetails = { status: 'ASSIGNED', retryCount: 0 };
      expect(isTaskInTerminalState(queueDetails)).toBe(false);
    });

    it('should return false for PENDING status without max retries', () => {
      const queueDetails = {
        status: 'PENDING',
        retryCount: 1,
        lastFailureReason: 'Temporary error',
      };
      expect(isTaskInTerminalState(queueDetails)).toBe(false);
    });

    it('should return false for FAILED status with retries remaining', () => {
      const queueDetails = {
        status: 'FAILED',
        retryCount: 1,
        permanentlyFailed: false,
      };
      expect(isTaskInTerminalState(queueDetails)).toBe(false);
    });

    it('should return false for CANCELLING status', () => {
      const queueDetails = { status: 'CANCELLING', retryCount: 0 };
      expect(isTaskInTerminalState(queueDetails)).toBe(false);
    });

    it('should handle PascalCase field names', () => {
      const queueDetails = {
        Status: 'COMPLETED',
        RetryCount: 0,
      };
      expect(isTaskInTerminalState(queueDetails)).toBe(true);
    });

    it('should handle mixed case field names', () => {
      const queueDetails = {
        Status: 'PENDING',
        retryCount: STALE_TASK_CONSTANTS.MAX_RETRY_COUNT,
        LastFailureReason: 'Error occurred',
      };
      expect(isTaskInTerminalState(queueDetails)).toBe(true);
    });
  });
});
