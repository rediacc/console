export interface TelemetryConfig {
  serviceName: string;
  serviceVersion: string;
  environment: string;
  endpoint: string;
  enabledInDevelopment?: boolean;
  samplingRate?: number;
  userConsent?: boolean;
  enableAutoInstrumentation?: boolean;
  enableWebVitals?: boolean;
}

export interface UserContext {
  userId?: string;
  email?: string;
  company?: string;
  sessionId: string;
  teamName?: string;
}

export interface WebVitalsMetric {
  name: string;
  value: number;
  rating: 'good' | 'needs-improvement' | 'poor';
  delta?: number;
  id: string;
}

export type TelemetryDetailValue = string | number | boolean | null | undefined;
export type TelemetryContext = Record<string, TelemetryDetailValue>;

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
