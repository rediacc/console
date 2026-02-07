import { test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError } from '../../src/utils/errors';

/**
 * Negative test cases for queue commands.
 */
test.describe('Queue Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;

  test.beforeAll(() => {
    runner = CliTestRunner.fromGlobalState();
  });

  test.describe('CancelQueueItem errors', () => {
    test('should fail when cancelling non-existent queue item', async () => {
      // Use a well-formed but non-existent UUID
      const fakeTaskId = '00000000-0000-0000-0000-000000000000';
      const result = await runner.run(['queue', 'cancel', fakeTaskId]);
      expectError(runner, result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });
  });

  test.describe('DeleteQueueItem errors', () => {
    test('should fail when deleting non-existent queue item', async () => {
      const fakeTaskId = '00000000-0000-0000-0000-000000000000';
      const result = await runner.run(['queue', 'delete', fakeTaskId, '--force']);
      expectError(runner, result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });
  });

  test.describe('RetryFailedQueueItem errors', () => {
    test('should fail when retrying non-existent queue item', async () => {
      const fakeTaskId = '00000000-0000-0000-0000-000000000000';
      const result = await runner.run(['queue', 'retry', fakeTaskId]);
      expectError(runner, result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });
  });

  test.describe('GetQueueItemTrace errors', () => {
    test('should fail when tracing non-existent queue item', async () => {
      const fakeTaskId = '00000000-0000-0000-0000-000000000000';
      const result = await runner.queueTrace(fakeTaskId);
      expectError(runner, result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });
  });

  test.describe('Queue filter priority errors', () => {
    test('should fail when filtering with min priority less than 1', async () => {
      const result = await runner.run(['queue', 'list', '--priority-min', '0']);
      expectError(runner, result, { messageContains: ErrorPatterns.QUEUE_PRIORITY_MIN_INVALID });
    });

    test('should fail when filtering with min priority greater than 5', async () => {
      const result = await runner.run(['queue', 'list', '--priority-min', '6']);
      expectError(runner, result, { messageContains: ErrorPatterns.QUEUE_PRIORITY_MIN_INVALID });
    });

    test('should fail when filtering with max priority less than 1', async () => {
      const result = await runner.run(['queue', 'list', '--priority-max', '0']);
      expectError(runner, result, { messageContains: ErrorPatterns.QUEUE_PRIORITY_MAX_INVALID });
    });

    test('should fail when filtering with max priority greater than 5', async () => {
      const result = await runner.run(['queue', 'list', '--priority-max', '6']);
      expectError(runner, result, { messageContains: ErrorPatterns.QUEUE_PRIORITY_MAX_INVALID });
    });
  });
});
