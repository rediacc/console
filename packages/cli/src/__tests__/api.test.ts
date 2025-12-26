import { describe, expect, it } from 'vitest';
import { CliApiError } from '../services/api.js';
import { EXIT_CODES } from '../types/index.js';

describe('CliApiError', () => {
  describe('constructor', () => {
    it('should create error with message only', () => {
      const error = new CliApiError('Test error');

      expect(error.message).toBe('Test error');
      expect(error.code).toBe('GENERAL_ERROR');
      expect(error.exitCode).toBe(EXIT_CODES.GENERAL_ERROR);
      expect(error.details).toEqual([]);
      expect(error.response).toBeUndefined();
    });

    it('should create error with all parameters', () => {
      const mockResponse = {
        failure: 404,
        message: 'Not found',
        errors: [],
        resultSets: [],
      };

      const error = new CliApiError(
        'Resource not found',
        'NOT_FOUND',
        EXIT_CODES.NOT_FOUND,
        ['Resource does not exist', 'Check the ID'],
        mockResponse
      );

      expect(error.message).toBe('Resource not found');
      expect(error.code).toBe('NOT_FOUND');
      expect(error.exitCode).toBe(EXIT_CODES.NOT_FOUND);
      expect(error.details).toEqual(['Resource does not exist', 'Check the ID']);
      expect(error.response).toBe(mockResponse);
    });

    it('should be an instance of Error', () => {
      const error = new CliApiError('Test');

      expect(error).toBeInstanceOf(Error);
      expect(error.name).toBe('CliApiError');
    });
  });

  describe('error codes', () => {
    it('should support AUTH_REQUIRED code', () => {
      const error = new CliApiError('Login required', 'AUTH_REQUIRED', EXIT_CODES.AUTH_REQUIRED);

      expect(error.code).toBe('AUTH_REQUIRED');
      expect(error.exitCode).toBe(EXIT_CODES.AUTH_REQUIRED);
    });

    it('should support PERMISSION_DENIED code', () => {
      const error = new CliApiError(
        'Access denied',
        'PERMISSION_DENIED',
        EXIT_CODES.PERMISSION_DENIED
      );

      expect(error.code).toBe('PERMISSION_DENIED');
      expect(error.exitCode).toBe(EXIT_CODES.PERMISSION_DENIED);
    });

    it('should support NETWORK_ERROR code', () => {
      const error = new CliApiError('Connection failed', 'NETWORK_ERROR', EXIT_CODES.NETWORK_ERROR);

      expect(error.code).toBe('NETWORK_ERROR');
      expect(error.exitCode).toBe(EXIT_CODES.NETWORK_ERROR);
    });

    it('should support SERVER_ERROR code', () => {
      const error = new CliApiError('Internal server error', 'SERVER_ERROR', EXIT_CODES.API_ERROR);

      expect(error.code).toBe('SERVER_ERROR');
      expect(error.exitCode).toBe(EXIT_CODES.API_ERROR);
    });

    it('should support INVALID_REQUEST code', () => {
      const error = new CliApiError('Bad request', 'INVALID_REQUEST', EXIT_CODES.INVALID_ARGUMENTS);

      expect(error.code).toBe('INVALID_REQUEST');
      expect(error.exitCode).toBe(EXIT_CODES.INVALID_ARGUMENTS);
    });
  });
});
