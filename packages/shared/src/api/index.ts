export * from './adapters';
// Client factory and adapters
export * from './client';
export * from './errorUtils';
export * from './normalizer';
export * from './parseResponse';
// Parsers - export all including base extraction utilities
export * from './parsers';
export * from './services';
export * from './statusCodes';
export * from './tokenUtils';
export type {
  PrimaryResult,
  ResultAtIndex,
  TypedApi,
  TypedApiConfig,
  TypedApiResponse,
} from './typedApi';
// TypedApi - only export the factory and types, not extractors (use parsers instead)
export { createTypedApi } from './typedApi';
