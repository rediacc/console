/**
 * Shared telemetry module.
 * Provides types and utilities for consistent telemetry across web and CLI.
 */

// Types
export type {
  TelemetryConfig,
  TelemetryContext,
  TelemetryMetric,
  UserContext,
} from './types';

// Utilities
export {
  anonymizeArgs,
  anonymizeEmail,
  anonymizeObject,
  anonymizeValue,
  enrichAttributes,
  errorToAttributes,
  extractApiEndpoint,
  generateSessionId,
  isSensitiveKey,
} from './utils';
