export * from './adapters/index.js';
// Client factory and adapters
export * from './client/index.js';
export * from './errorUtils';
export * from './normalizer';
export * from './parseResponse';
// Parsers - export all including base extraction utilities
export * from './parsers/index.js';
export * from './services/index.js';
export * from './statusCodes';
export * from './tokenUtils';
export type {
  PrimaryResult,
  ResultAtIndex,
  TypedApi,
  TypedApiConfig,
  TypedApiResponse,
} from './typedApi/index.js';
// TypedApi - only export the factory and types, not extractors (use parsers instead)
export { createTypedApi } from './typedApi/index.js';
