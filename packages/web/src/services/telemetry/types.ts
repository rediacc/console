// Re-export shared types
export type {
  TelemetryConfig,
  TelemetryContext,
  TelemetryMetric,
  UserContext,
} from '@rediacc/shared/telemetry';

// Alias for backward compatibility
export type { TelemetryMetric as WebVitalsMetric } from '@rediacc/shared/telemetry';

export interface LayoutShiftEntry extends PerformanceEntry {
  value: number;
  hadRecentInput?: boolean;
}

export interface ExtendedPerformance {
  memory?: {
    jsHeapSizeLimit: number;
    usedJSHeapSize: number;
    totalJSHeapSize: number;
  };
}

export interface NavigatorConnection {
  effectiveType?: string;
  downlink?: number;
  rtt?: number;
}

export interface WindowNavigation {
  type?: string;
}
