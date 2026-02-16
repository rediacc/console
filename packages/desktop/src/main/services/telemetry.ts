import { trace } from '@opentelemetry/api';
import log from 'electron-log';

class DesktopTelemetryService {
  private readonly tracer = trace.getTracer('rediacc-desktop');

  trackEvent(eventName: string, attributes?: Record<string, unknown>): void {
    log.info(`[telemetry] ${eventName}`, attributes ?? {});

    const span = this.tracer.startSpan(eventName);
    if (attributes) {
      for (const [key, value] of Object.entries(attributes)) {
        if (value !== undefined && value !== null) {
          span.setAttribute(key, String(value));
        }
      }
    }
    span.end();
  }
}

export const desktopTelemetryService = new DesktopTelemetryService();
