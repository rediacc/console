import { context, propagation, trace } from '@opentelemetry/api';
import { getWebAutoInstrumentations } from '@opentelemetry/auto-instrumentations-web';
import { ZoneContextManager } from '@opentelemetry/context-zone';
import {
  CompositePropagator,
  W3CBaggagePropagator,
  W3CTraceContextPropagator,
} from '@opentelemetry/core';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { resourceFromAttributes } from '@opentelemetry/resources';
import {
  BatchSpanProcessor,
  SimpleSpanProcessor,
  TraceIdRatioBasedSampler,
  WebTracerProvider,
} from '@opentelemetry/sdk-trace-web';
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
  ATTR_USER_AGENT_ORIGINAL,
} from '@opentelemetry/semantic-conventions';
import {
  extractApiEndpoint,
  generateSessionId,
  getBrowserName,
  getBrowserVersion,
  getNavigationType,
  getPageLoadTime,
  getPerformanceAttributes,
  getPlatform,
} from './telemetry/browserUtils';
import { initializeWebVitals } from './telemetry/webVitals';
import type {
  TelemetryConfig,
  TelemetryContext,
  UserContext,
  WebVitalsMetric,
} from './telemetry/types';

class TelemetryService {
  private provider: WebTracerProvider | null = null;
  private isInitialized = false;
  private config: TelemetryConfig | null = null;
  private userContext: UserContext | null = null;
  private sessionStartTime = Date.now();
  private webVitalsObserver: PerformanceObserver | null = null;

  async initialize(config: TelemetryConfig): Promise<void> {
    if (this.isInitialized) return;

    this.config = config;

    if (!this.shouldEnableTelemetry()) {
      console.warn('Telemetry disabled - development mode or user consent not granted');
      return;
    }

    try {
      const contextManager = new ZoneContextManager();
      context.setGlobalContextManager(contextManager);

      propagation.setGlobalPropagator(
        new CompositePropagator({
          propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()],
        })
      );

      const resource = resourceFromAttributes({
        [ATTR_SERVICE_NAME]: config.serviceName,
        [ATTR_SERVICE_VERSION]: config.serviceVersion,
        'deployment.environment': config.environment,
        [ATTR_USER_AGENT_ORIGINAL]: navigator.userAgent,
        'service.component': 'frontend',
        'service.platform': 'web',
        'service.framework': 'react',
        'browser.name': getBrowserName(),
        'browser.version': getBrowserVersion(),
        'browser.language': navigator.language,
        'browser.platform': getPlatform(),
        'screen.resolution': `${screen.width}x${screen.height}`,
        'screen.color_depth': screen.colorDepth,
        'session.id': generateSessionId(),
        'telemetry.sdk.name': 'opentelemetry',
        'telemetry.sdk.version': '2.0',
      });

      const traceExporter = new OTLPTraceExporter({
        url: `${config.endpoint}/v1/traces`,
        headers: { 'Content-Type': 'application/json' },
        timeoutMillis: 10000,
      });

      const spanProcessor =
        config.environment === 'development'
          ? new SimpleSpanProcessor(traceExporter)
          : new BatchSpanProcessor(traceExporter, {
              maxQueueSize: 2048,
              maxExportBatchSize: 512,
              scheduledDelayMillis: 5000,
              exportTimeoutMillis: 30000,
            });

      this.provider = new WebTracerProvider({
        resource,
        sampler: new TraceIdRatioBasedSampler(config.samplingRate || 0.1),
        spanProcessors: [spanProcessor],
      });

      this.provider.register({
        contextManager,
        propagator: new CompositePropagator({
          propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()],
        }),
      });

      if (config.enableAutoInstrumentation !== false) {
        try {
          registerInstrumentations({
            instrumentations: [
              getWebAutoInstrumentations({
                '@opentelemetry/instrumentation-fetch': {
                  propagateTraceHeaderCorsUrls: [/.*/],
                  clearTimingResources: true,
                },
                '@opentelemetry/instrumentation-xml-http-request': {
                  propagateTraceHeaderCorsUrls: [/.*/],
                },
                '@opentelemetry/instrumentation-user-interaction': {
                  eventNames: ['click', 'submit', 'keydown', 'change'],
                },
                '@opentelemetry/instrumentation-document-load': { enabled: true },
              }),
            ],
          });
        } catch (error) {
          console.warn('Failed to register auto-instrumentations:', error);
        }
      }

      this.isInitialized = true;

      if (config.enableWebVitals !== false) {
        this.webVitalsObserver = initializeWebVitals((metric) => this.trackWebVitals(metric));
      }

      this.trackEvent('telemetry.initialized', {
        'telemetry.version': config.serviceVersion,
        'telemetry.endpoint': config.endpoint,
        'telemetry.auto_instrumentation': config.enableAutoInstrumentation !== false,
        'telemetry.web_vitals': config.enableWebVitals !== false,
        'browser.supports_performance_api': 'performance' in window,
        'browser.supports_navigation_api': 'navigation' in window,
        'browser.supports_observer_api': 'PerformanceObserver' in window,
      });
    } catch (error) {
      console.error('Failed to initialize telemetry:', error);
    }
  }

  setUserContext(userContext: Partial<UserContext>): void {
    this.userContext = {
      ...this.userContext,
      sessionId: this.userContext?.sessionId || generateSessionId(),
      ...userContext,
    };

    if (this.isInitialized && this.userContext) {
      try {
        const entries: Record<string, { value: string }> = {};
        if (this.userContext.sessionId) {
          entries['session.id'] = { value: this.userContext.sessionId };
        }
        if (this.userContext.email) {
          const emailDomain = this.userContext.email.split('@')[1];
          if (emailDomain) {
            entries['user.email_domain'] = { value: emailDomain };
          }
        }
        void entries; // Baggage is propagated via HTTP headers automatically
      } catch (error) {
        console.warn('Failed to set baggage context:', error);
      }
    }
  }

  trackEvent(eventName: string, attributes: Record<string, string | number | boolean> = {}): void {
    if (!this.isInitialized) return;

    const tracer = trace.getTracer('rediacc-console-events', '2.0.0');
    const span = tracer.startSpan(eventName);

    try {
      const enrichedAttributes = {
        ...attributes,
        'event.name': eventName,
        'event.timestamp': Date.now(),
        'session.duration_ms': Date.now() - this.sessionStartTime,
        'page.url': window.location.href,
        'page.path': window.location.pathname,
        'page.title': document.title,
        'page.referrer': document.referrer,
        ...this.getUserAttributes(),
        ...getPerformanceAttributes(),
      };

      Object.entries(enrichedAttributes).forEach(([key, value]) => {
        span.setAttributes({ [key]: value });
      });

      span.setStatus({ code: 1 });
    } catch (error) {
      span.setStatus({ code: 2, message: String(error) });
      console.error('Error tracking event:', error);
    } finally {
      span.end();
    }
  }

  trackPageView(path: string, title?: string): void {
    this.trackEvent('page.view', {
      'page.path': path,
      'page.title': title || document.title,
      'page.referrer': document.referrer,
      'navigation.type': getNavigationType(),
      'page.load_time': getPageLoadTime(),
    });
  }

  trackUserAction(action: string, target?: string, details: TelemetryContext = {}): void {
    this.trackEvent('user.action', {
      'user.action.type': action,
      'user.action.target': target || 'unknown',
      'user.action.timestamp': Date.now(),
      ...Object.fromEntries(
        Object.entries(details).map(([key, value]) => [`user.action.${key}`, String(value)])
      ),
    });
  }

  trackApiCall(
    method: string,
    url: string,
    statusCode?: number,
    duration?: number,
    error?: string
  ): void {
    this.trackEvent('api.call', {
      'http.method': method,
      'http.url': url,
      'http.status_code': statusCode || 0,
      'http.duration_ms': duration || 0,
      'http.error': error || '',
      'http.success': !error && statusCode && statusCode < 400 ? true : false,
      'api.endpoint': extractApiEndpoint(url),
    });
  }

  trackError(error: Error, telemetryContext: TelemetryContext = {}): void {
    this.trackEvent('error.occurred', {
      'error.type': error.constructor.name,
      'error.message': error.message,
      'error.stack': error.stack || '',
      'error.timestamp': Date.now(),
      ...Object.fromEntries(
        Object.entries(telemetryContext).map(([key, value]) => [
          `error.context.${key}`,
          String(value),
        ])
      ),
    });
  }

  trackPerformance(metric: string, value: number, unit: string = 'ms'): void {
    this.trackEvent('performance.metric', {
      'performance.metric.name': metric,
      'performance.metric.value': value,
      'performance.metric.unit': unit,
      'performance.navigation_type': getNavigationType(),
    });
  }

  trackWebVitals(metric: WebVitalsMetric): void {
    this.trackEvent('web_vitals.metric', {
      'web_vitals.name': metric.name,
      'web_vitals.value': metric.value,
      'web_vitals.rating': metric.rating,
      'web_vitals.delta': metric.delta || 0,
      'web_vitals.id': metric.id,
    });
  }

  measureAndTrack<T>(name: string, fn: () => T | Promise<T>): T | Promise<T> {
    const tracer = trace.getTracer('rediacc-console-performance', '2.0.0');

    return tracer.startActiveSpan(name, (span) => {
      const startTime = performance.now();

      try {
        const result = fn();

        if (result instanceof Promise) {
          return result.then(
            (value) => {
              const duration = performance.now() - startTime;
              span.setAttributes({ 'performance.duration_ms': duration, 'performance.success': true });
              span.setStatus({ code: 1 });
              span.end();
              this.trackPerformance(name, duration);
              return value;
            },
            (error) => {
              const duration = performance.now() - startTime;
              span.setAttributes({
                'performance.duration_ms': duration,
                'performance.success': false,
                'performance.error': error.message,
              });
              span.setStatus({ code: 2, message: error.message });
              span.end();
              this.trackPerformance(`${name}.error`, duration);
              throw error;
            }
          );
        } else {
          const duration = performance.now() - startTime;
          span.setAttributes({ 'performance.duration_ms': duration, 'performance.success': true });
          span.setStatus({ code: 1 });
          span.end();
          this.trackPerformance(name, duration);
          return result;
        }
      } catch (error) {
        const duration = performance.now() - startTime;
        span.setAttributes({
          'performance.duration_ms': duration,
          'performance.success': false,
          'performance.error': (error as Error).message,
        });
        span.setStatus({ code: 2, message: (error as Error).message });
        span.end();
        this.trackPerformance(`${name}.error`, duration);
        throw error;
      }
    });
  }

  async shutdown(): Promise<void> {
    if (this.provider && this.isInitialized) {
      this.trackEvent('telemetry.shutdown');
      if (this.webVitalsObserver) {
        this.webVitalsObserver.disconnect();
        this.webVitalsObserver = null;
      }
      await this.provider.shutdown();
      this.isInitialized = false;
    }
  }

  private shouldEnableTelemetry(): boolean {
    if (!this.config) return false;
    if (import.meta.env.DEV && !this.config.enabledInDevelopment) return false;
    if (this.config.userConsent !== undefined && !this.config.userConsent) return false;
    return true;
  }

  private getUserAttributes(): Record<string, string> {
    if (!this.userContext) return {};

    const attributes: Record<string, string> = {};
    if (this.userContext.sessionId) attributes['user.session_id'] = this.userContext.sessionId;
    if (this.userContext.email)
      attributes['user.email_domain'] = this.userContext.email.split('@')[1] || '';
    if (this.userContext.company) attributes['user.company'] = this.userContext.company;
    if (this.userContext.teamName) attributes['user.team'] = this.userContext.teamName;
    return attributes;
  }
}

// Create singleton instance
export const telemetryService = new TelemetryService();

// Export configuration helper
export const createTelemetryConfig = (): TelemetryConfig => {
  const isDev = import.meta.env.DEV;

  const getObsEndpoint = () => {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'https://www.rediacc.com/otlp';
    }
    return `https://${hostname}/otlp`;
  };

  return {
    serviceName: 'rediacc-console',
    serviceVersion: import.meta.env.VITE_APP_VERSION || '2.0.0',
    environment: isDev ? 'development' : 'production',
    endpoint: getObsEndpoint(),
    enabledInDevelopment: true,
    samplingRate: isDev ? 1.0 : 0.1,
    userConsent: true,
    enableAutoInstrumentation: true,
    enableWebVitals: true,
  };
};

// Re-export types for consumers
export type { TelemetryConfig, TelemetryContext, UserContext, WebVitalsMetric } from './telemetry/types';
