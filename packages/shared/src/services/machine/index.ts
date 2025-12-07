/**
 * Machine services barrel export
 * Consolidates all machine-related services for both CLI and Web
 */

// Parsing services (vault status, repo deployment)
export * from './parsing';

// Assignment services (type detection, conflict checking)
export * from './assignment';

// Validation services (exclusivity rules, bulk validation)
export * from './validation';

// Type definitions
export * from './types';
