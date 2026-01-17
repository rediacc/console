// Re-export shared types
// Alias for backward compatibility
export type {
  TelemetryConfig,
  TelemetryContext,
  TelemetryMetric as WebVitalsMetric,
  UserContext,
} from '@rediacc/shared/telemetry';

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
