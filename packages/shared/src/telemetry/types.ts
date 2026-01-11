/**
 * Shared telemetry types for web and CLI.
 * Platform-specific types remain in their respective packages.
 */

/**
 * Configuration for telemetry initialization.
 */
export interface TelemetryConfig {
  serviceName: string;
  serviceVersion: string;
  environment: string;
  endpoint: string;
  enabledInDevelopment?: boolean;
  samplingRate?: number;
  userConsent?: boolean;
  /** Web-specific: enable OpenTelemetry auto-instrumentation */
  enableAutoInstrumentation?: boolean;
  /** Web-specific: enable Web Vitals tracking */
  enableWebVitals?: boolean;
}

/**
 * User context for telemetry attribution.
 */
export interface UserContext {
  userId?: string;
  email?: string;
  organization?: string;
  sessionId: string;
  teamName?: string;
}

/**
 * Generic telemetry metric (e.g., Web Vitals, performance metrics).
 */
export interface TelemetryMetric {
  name: string;
  value: number;
  rating?: 'good' | 'needs-improvement' | 'poor';
  delta?: number;
  id: string;
}

/**
 * Value types allowed in telemetry context.
 */
type TelemetryDetailValue = string | number | boolean | null | undefined;

/**
 * Context object for telemetry events.
 */
export type TelemetryContext = Record<string, TelemetryDetailValue>;
