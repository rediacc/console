import type { TelemetryHandler } from '@rediacc/shared/api';
import { telemetryService } from '@/services/telemetryService';

/**
 * Web telemetry handler wrapping the telemetryService.
 * Sends API call metrics to the observability backend.
 */
export const telemetryAdapter: TelemetryHandler = {
  trackApiCall: (
    method: string,
    url: string,
    status: number | undefined,
    duration: number,
    error?: string
  ) => telemetryService.trackApiCall(method, url, status, duration, error),
};
