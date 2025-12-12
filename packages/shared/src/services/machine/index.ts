/**
 * Machine services barrel export
 * Consolidates all machine-related services for both CLI and Web
 */

// Assignment services (type detection, conflict checking)
export * from './assignment';
// Parsing services (vault status, repository deployment)
export * from './parsing';
// Type definitions
export * from './types';
// Validation services (exclusivity rules, bulk validation)
export * from './validation';
