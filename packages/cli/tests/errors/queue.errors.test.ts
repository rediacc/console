import { describe, it } from 'vitest';
import { runCli } from '../helpers/cli.js';
import { ErrorPatterns, expectError } from '../helpers/errors.js';

/**
 * Negative test cases for queue commands.
 * Tests backend error responses from middleware stored procedures.
 *
 * Note: Most queue error scenarios require complex setup (creating queue items,
 * waiting for specific states, etc.). This test suite focuses on simple error
 * cases that can be tested without extensive setup.
 */
describe('queue error scenarios', () => {
  // ============================================
  // CancelQueueItem Errors
  // ============================================
  describe('CancelQueueItem errors', () => {
    it('should fail when cancelling non-existent queue item', async () => {
      // Use a well-formed but non-existent UUID
      const fakeTaskId = '00000000-0000-0000-0000-000000000000';
      const result = await runCli(['queue', 'cancel', fakeTaskId]);
      expectError(result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });

    // Note: Testing "already cancelled" and "cannot cancel completed/failed" requires
    // creating queue items and manipulating their state, which is complex and
    // time-consuming. These scenarios are better tested through integration tests
    // or manual testing.
  });

  // ============================================
  // DeleteQueueItem Errors
  // ============================================
  describe('DeleteQueueItem errors', () => {
    it('should fail when deleting non-existent queue item', async () => {
      const fakeTaskId = '00000000-0000-0000-0000-000000000000';
      const result = await runCli(['queue', 'delete', fakeTaskId, '--force']);
      expectError(result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });
  });

  // ============================================
  // RetryFailedQueueItem Errors
  // ============================================
  describe('RetryFailedQueueItem errors', () => {
    it('should fail when retrying non-existent queue item', async () => {
      const fakeTaskId = '00000000-0000-0000-0000-000000000000';
      const result = await runCli(['queue', 'retry', fakeTaskId]);
      expectError(result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });

    // Note: Testing "can only retry failed items" requires creating a queue item
    // in a non-FAILED state, which is complex. This is better tested through
    // integration tests.
  });

  // ============================================
  // GetQueueItemTrace Errors
  // ============================================
  describe('GetQueueItemTrace errors', () => {
    it('should fail when tracing non-existent queue item', async () => {
      const fakeTaskId = '00000000-0000-0000-0000-000000000000';
      const result = await runCli(['queue', 'trace', fakeTaskId]);
      expectError(result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });
  });

  // ============================================
  // Company Errors (from db_middleware_company.sql)
  // ============================================
  // The following company ErrorPatterns related to queues exist:
  //
  // TESTABLE via filter parameters:
  // - QUEUE_PRIORITY_MIN_INVALID - tested below (priority filter min)
  // - QUEUE_PRIORITY_MAX_INVALID - tested below (priority filter max)
  //
  // NOT TESTABLE (require queue creation with vault data):
  // - QUEUE_PARAM_INVALID_CHARS - requires vault with invalid characters
  // - QUEUE_PRIORITY_INVALID - requires priority outside 1-5 range during create

  describe('Queue filter priority errors', () => {
    it('should fail when filtering with min priority less than 1', async () => {
      const result = await runCli(['queue', 'list', '--priority-min', '0']);
      expectError(result, { messageContains: ErrorPatterns.QUEUE_PRIORITY_MIN_INVALID });
    });

    it('should fail when filtering with min priority greater than 5', async () => {
      const result = await runCli(['queue', 'list', '--priority-min', '6']);
      expectError(result, { messageContains: ErrorPatterns.QUEUE_PRIORITY_MIN_INVALID });
    });

    it('should fail when filtering with max priority less than 1', async () => {
      const result = await runCli(['queue', 'list', '--priority-max', '0']);
      expectError(result, { messageContains: ErrorPatterns.QUEUE_PRIORITY_MAX_INVALID });
    });

    it('should fail when filtering with max priority greater than 5', async () => {
      const result = await runCli(['queue', 'list', '--priority-max', '6']);
      expectError(result, { messageContains: ErrorPatterns.QUEUE_PRIORITY_MAX_INVALID });
    });
  });
});
