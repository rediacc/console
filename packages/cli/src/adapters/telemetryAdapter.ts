/**
 * Telemetry adapter for CLI API client integration.
 * Forwards API call tracking to the telemetry service.
 */

import type { TelemetryHandler } from '@rediacc/shared/api';
import { telemetryService } from '../services/telemetry.js';

/**
 * Telemetry adapter that implements the TelemetryHandler interface.
 * Delegates all tracking to the CLI telemetry service.
 */
export const telemetryAdapter: TelemetryHandler = {
  trackApiCall: (method, url, status, duration, error) => {
    telemetryService.trackApiCall(method, url, status, duration, error);
  },

  trackEvent: (eventName, attributes) => {
    telemetryService.trackEvent(eventName, attributes);
  },

  trackError: (error, context) => {
    telemetryService.trackError(error, context);
  },

  trackMetric: (name, value, unit) => {
    telemetryService.trackMetric(name, value, unit);
  },

  setUserContext: (context) => {
    telemetryService.setUserContext(context);
  },

  initialize: (config) => {
    telemetryService.initialize(config);
  },

  shutdown: () => {
    return telemetryService.shutdown();
  },
};
