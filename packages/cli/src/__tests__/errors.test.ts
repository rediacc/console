import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EXIT_CODES } from '../types/index.js';

// Mock dependencies before importing the module
vi.mock('../services/output.js', () => ({
  outputService: {
    error: vi.fn(),
  },
}));

// Import after mocking
import { outputService } from '../services/output.js';
import {
  handleError,
  setOutputFormat,
  ValidationError,
  normalizeError,
} from '../utils/errors.js';
import { CliApiError } from '../services/api.js';

describe('Error Handling', () => {
  let mockExit: ReturnType<typeof vi.spyOn>;
  let mockConsoleLog: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockExit = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never);
    mockConsoleLog = vi.spyOn(console, 'log').mockImplementation(() => {});
    setOutputFormat('table'); // Reset to default
  });

  afterEach(() => {
    mockExit.mockRestore();
    mockConsoleLog.mockRestore();
  });

  describe('ValidationError', () => {
    it('should be an instance of Error', () => {
      const error = new ValidationError('Test message');
      expect(error).toBeInstanceOf(Error);
      expect(error.name).toBe('ValidationError');
      expect(error.message).toBe('Test message');
    });
  });

  describe('normalizeError', () => {
    it('should normalize ValidationError', () => {
      const error = new ValidationError('Invalid input');
      const result = normalizeError(error);

      expect(result.code).toBe('VALIDATION_ERROR');
      expect(result.message).toBe('Invalid input');
      expect(result.exitCode).toBe(EXIT_CODES.INVALID_ARGUMENTS);
    });

    it('should normalize CliApiError', () => {
      const error = new CliApiError(
        'Not found',
        'NOT_FOUND',
        EXIT_CODES.NOT_FOUND,
        ['Resource does not exist']
      );
      const result = normalizeError(error);

      expect(result.code).toBe('NOT_FOUND');
      expect(result.message).toBe('Not found');
      expect(result.exitCode).toBe(EXIT_CODES.NOT_FOUND);
      expect(result.details).toEqual(['Resource does not exist']);
    });

    it('should normalize generic Error', () => {
      const error = new Error('Something went wrong');
      const result = normalizeError(error);

      expect(result.code).toBe('GENERAL_ERROR');
      expect(result.message).toBe('Something went wrong');
      expect(result.exitCode).toBe(EXIT_CODES.GENERAL_ERROR);
    });

    it('should normalize non-Error values', () => {
      const result = normalizeError('string error');

      expect(result.code).toBe('GENERAL_ERROR');
      expect(result.message).toBe('string error');
      expect(result.exitCode).toBe(EXIT_CODES.GENERAL_ERROR);
    });
  });

  describe('handleError in table mode', () => {
    beforeEach(() => {
      setOutputFormat('table');
    });

    it('should output error message to stderr', () => {
      const error = new Error('Test error');
      handleError(error);

      expect(outputService.error).toHaveBeenCalledWith('Error: Test error');
      expect(mockExit).toHaveBeenCalledWith(EXIT_CODES.GENERAL_ERROR);
    });

    it('should output details for CliApiError', () => {
      const error = new CliApiError('API failed', 'SERVER_ERROR', EXIT_CODES.API_ERROR, [
        'Detail 1',
        'Detail 2',
      ]);
      handleError(error);

      expect(outputService.error).toHaveBeenCalledWith('Error: API failed');
      expect(outputService.error).toHaveBeenCalledWith('  - Detail 1');
      expect(outputService.error).toHaveBeenCalledWith('  - Detail 2');
      expect(mockExit).toHaveBeenCalledWith(EXIT_CODES.API_ERROR);
    });

    it('should not duplicate message in details', () => {
      const error = new CliApiError('Same message', 'SERVER_ERROR', EXIT_CODES.API_ERROR, [
        'Same message',
      ]);
      handleError(error);

      // Should only call error once for the main message, not for duplicate detail
      expect(outputService.error).toHaveBeenCalledTimes(1);
    });
  });

  describe('handleError in JSON mode', () => {
    beforeEach(() => {
      setOutputFormat('json');
    });

    it('should output JSON to stdout', () => {
      const error = new Error('Test error');
      handleError(error);

      expect(mockConsoleLog).toHaveBeenCalled();
      const output = JSON.parse(mockConsoleLog.mock.calls[0][0]);

      expect(output.success).toBe(false);
      expect(output.error.code).toBe('GENERAL_ERROR');
      expect(output.error.message).toBe('Test error');
      expect(output.exitCode).toBe(EXIT_CODES.GENERAL_ERROR);
    });

    it('should include details in JSON output', () => {
      const error = new CliApiError('API failed', 'NOT_FOUND', EXIT_CODES.NOT_FOUND, [
        'Resource missing',
      ]);
      handleError(error);

      const output = JSON.parse(mockConsoleLog.mock.calls[0][0]);

      expect(output.error.details).toEqual(['Resource missing']);
    });

    it('should not include empty details array', () => {
      const error = new ValidationError('Invalid');
      handleError(error);

      const output = JSON.parse(mockConsoleLog.mock.calls[0][0]);

      expect(output.error.details).toBeUndefined();
    });
  });

  describe('exit codes', () => {
    it('should use correct exit code for ValidationError', () => {
      setOutputFormat('table');
      handleError(new ValidationError('Invalid'));
      expect(mockExit).toHaveBeenCalledWith(EXIT_CODES.INVALID_ARGUMENTS);
    });

    it('should use correct exit code for auth errors', () => {
      setOutputFormat('table');
      handleError(new CliApiError('Auth required', 'AUTH_REQUIRED', EXIT_CODES.AUTH_REQUIRED));
      expect(mockExit).toHaveBeenCalledWith(EXIT_CODES.AUTH_REQUIRED);
    });

    it('should use correct exit code for permission errors', () => {
      setOutputFormat('table');
      handleError(
        new CliApiError('Permission denied', 'PERMISSION_DENIED', EXIT_CODES.PERMISSION_DENIED)
      );
      expect(mockExit).toHaveBeenCalledWith(EXIT_CODES.PERMISSION_DENIED);
    });
  });
});
