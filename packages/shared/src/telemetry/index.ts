/**
 * Shared telemetry module.
 * Provides types and utilities for consistent telemetry across web and CLI.
 */

export { TELEMETRY_ATTRIBUTES, TELEMETRY_SUBSCRIPTION_SOURCES } from './attributes.js';
// Types
export type {
  TelemetryConfig,
  TelemetryContext,
  TelemetryMetric,
  UserContext,
} from './types.js';

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
} from './utils.js';
