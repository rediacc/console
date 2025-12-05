import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { resourceFromAttributes } from '@opentelemetry/resources';
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
  ATTR_USER_AGENT_ORIGINAL,
} from '@opentelemetry/semantic-conventions';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import {
  BatchSpanProcessor,
  SimpleSpanProcessor,
  TraceIdRatioBasedSampler,
} from '@opentelemetry/sdk-trace-web';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { getWebAutoInstrumentations } from '@opentelemetry/auto-instrumentations-web';
import { ZoneContextManager } from '@opentelemetry/context-zone';
import { trace, context, propagation } from '@opentelemetry/api';
import type { Span } from '@opentelemetry/api';
import {
  CompositePropagator,
  W3CTraceContextPropagator,
  W3CBaggagePropagator,
} from '@opentelemetry/core';

interface TelemetryConfig {
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

interface UserContext {
  userId?: string;
  email?: string;
  company?: string;
  sessionId: string;
  teamName?: string;
}

interface WebVitalsMetric {
  name: string;
  value: number;
  rating: 'good' | 'needs-improvement' | 'poor';
  delta?: number;
  id: string;
}

type TelemetryDetailValue = string | number | boolean | null | undefined;
type TelemetryContext = Record<string, TelemetryDetailValue>;

interface LayoutShiftEntry extends PerformanceEntry {
  value: number;
  hadRecentInput?: boolean;
}

interface ExtendedPerformance {
  memory?: {
    jsHeapSizeLimit: number;
    usedJSHeapSize: number;
    totalJSHeapSize: number;
  };
  navigation?: PerformanceNavigation;
  timing?: PerformanceTiming;
}

interface NavigatorConnection {
  effectiveType?: string;
  downlink?: number;
  rtt?: number;
}

interface WindowNavigation {
  type?: string;
}

class TelemetryService {
  private provider: WebTracerProvider | null = null;
  private isInitialized = false;
  private config: TelemetryConfig | null = null;
  private userContext: UserContext | null = null;
  private sessionStartTime = Date.now();
  private webVitalsObserver: PerformanceObserver | null = null;

  async initialize(config: TelemetryConfig): Promise<void> {
    if (this.isInitialized) {
      return;
    }

    this.config = config;

    // Check if telemetry should be enabled
    if (!this.shouldEnableTelemetry()) {
      console.warn('Telemetry disabled - development mode or user consent not granted');
      return;
    }

    try {
      // Set up context manager for better async context handling
      const contextManager = new ZoneContextManager();
      context.setGlobalContextManager(contextManager);

      // Set up propagators for distributed tracing
      propagation.setGlobalPropagator(
        new CompositePropagator({
          propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()],
        })
      );

      // Create resource with enhanced metadata
      const resource = resourceFromAttributes({
        [ATTR_SERVICE_NAME]: config.serviceName,
        [ATTR_SERVICE_VERSION]: config.serviceVersion,
        'deployment.environment': config.environment,
        [ATTR_USER_AGENT_ORIGINAL]: navigator.userAgent,
        'service.component': 'frontend',
        'service.platform': 'web',
        'service.framework': 'react',
        'browser.name': this.getBrowserName(),
        'browser.version': this.getBrowserVersion(),
        'browser.language': navigator.language,
        'browser.platform': navigator.platform || 'unknown',
        'screen.resolution': `${screen.width}x${screen.height}`,
        'screen.color_depth': screen.colorDepth,
        'session.id': this.generateSessionId(),
        'telemetry.sdk.name': 'opentelemetry',
        'telemetry.sdk.version': '2.0',
      });

      // Configure OTLP exporter with better error handling
      const traceExporter = new OTLPTraceExporter({
        url: `${config.endpoint}/v1/traces`,
        headers: {
          'Content-Type': 'application/json',
        },
        timeoutMillis: 10000,
      });

      // Use BatchSpanProcessor for production, SimpleSpanProcessor for development
      const spanProcessor =
        config.environment === 'development'
          ? new SimpleSpanProcessor(traceExporter)
          : new BatchSpanProcessor(traceExporter, {
              maxQueueSize: 2048,
              maxExportBatchSize: 512,
              scheduledDelayMillis: 5000,
              exportTimeoutMillis: 30000,
            });

      // Initialize tracer provider with span processors
      this.provider = new WebTracerProvider({
        resource,
        sampler: this.createSampler(config.samplingRate || 0.1),
        spanProcessors: [spanProcessor],
      });

      // Register the provider
      this.provider.register({
        contextManager: contextManager,
        propagator: new CompositePropagator({
          propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()],
        }),
      });

      // Set up auto-instrumentations if enabled
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
                '@opentelemetry/instrumentation-document-load': {
                  enabled: true,
                },
              }),
            ],
          });
        } catch (error) {
          console.warn('Failed to register auto-instrumentations:', error);
        }
      }

      this.isInitialized = true;

      // Initialize Web Vitals if enabled
      if (config.enableWebVitals !== false) {
        this.initializeWebVitals();
      }

      // Track initialization
      this.trackEvent('telemetry.initialized', {
        'telemetry.version': config.serviceVersion,
        'telemetry.endpoint': config.endpoint,
        'telemetry.auto_instrumentation': config.enableAutoInstrumentation !== false,
        'telemetry.web_vitals': config.enableWebVitals !== false,
        'browser.supports_performance_api': 'performance' in window,
        'browser.supports_navigation_api': 'navigation' in window,
        'browser.supports_observer_api': 'PerformanceObserver' in window,
      });

      // Initialization completed successfully
    } catch (error) {
      console.error('Failed to initialize telemetry:', error);
    }
  }

  setUserContext(userContext: Partial<UserContext>): void {
    this.userContext = {
      ...this.userContext,
      sessionId: this.userContext?.sessionId || this.generateSessionId(),
      ...userContext,
    };

    // Add user context to global baggage for distributed tracing
    if (this.isInitialized) {
      try {
        // Note: Baggage API has changed in newer versions
        // We create baggage entries but don't set them globally as this is handled by instrumentation
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

        // Baggage is propagated via HTTP headers automatically by instrumentation
        // Store for reference but don't attempt to set globally
        void entries;
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
      // Add common attributes with improved naming
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
        ...this.getPerformanceAttributes(),
      };

      // Set all attributes on the span
      Object.entries(enrichedAttributes).forEach(([key, value]) => {
        span.setAttributes({ [key]: value });
      });

      span.setStatus({ code: 1 }); // OK
    } catch (error) {
      span.setStatus({ code: 2, message: String(error) }); // ERROR
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
      'navigation.type': this.getNavigationType(),
      'page.load_time': this.getPageLoadTime(),
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
      'api.endpoint': this.extractApiEndpoint(url),
    });
  }

  trackError(error: Error, context: TelemetryContext = {}): void {
    this.trackEvent('error.occurred', {
      'error.type': error.constructor.name,
      'error.message': error.message,
      'error.stack': error.stack || '',
      'error.timestamp': Date.now(),
      ...Object.fromEntries(
        Object.entries(context).map(([key, value]) => [`error.context.${key}`, String(value)])
      ),
    });
  }

  trackPerformance(metric: string, value: number, unit: string = 'ms'): void {
    this.trackEvent('performance.metric', {
      'performance.metric.name': metric,
      'performance.metric.value': value,
      'performance.metric.unit': unit,
      'performance.navigation_type': this.getNavigationType(),
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
              span.setAttributes({
                'performance.duration_ms': duration,
                'performance.success': true,
              });
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
          span.setAttributes({
            'performance.duration_ms': duration,
            'performance.success': true,
          });
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

      // Disconnect web vitals observer
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

    // Check development mode
    if (import.meta.env.DEV && !this.config.enabledInDevelopment) {
      return false;
    }

    // Check user consent
    if (this.config.userConsent !== undefined && !this.config.userConsent) {
      return false;
    }

    return true;
  }

  private createSampler(samplingRate: number) {
    // Use built-in sampling for better performance
    return new TraceIdRatioBasedSampler(samplingRate);
  }

  private initializeWebVitals(): void {
    // Use the web-vitals library for accurate Core Web Vitals measurement
    if (typeof window !== 'undefined' && 'web-vitals' in window) {
      // This would be imported from web-vitals package
      // import { getCLS, getFID, getFCP, getLCP, getTTFB } from 'web-vitals'
      console.warn('Web Vitals tracking enabled - implement with web-vitals package');
    } else {
      // Fallback to manual performance observer
      this.setupManualWebVitals();
    }
  }

  private setupManualWebVitals(): void {
    if ('PerformanceObserver' in window) {
      // Cumulative Layout Shift
      const clsObserver = new PerformanceObserver((list) => {
        let clsValue = 0;
        list.getEntries().forEach((entry) => {
          const layoutEntry = entry as LayoutShiftEntry;
          if (!layoutEntry.hadRecentInput) {
            clsValue += layoutEntry.value;
          }
        });
        if (clsValue > 0) {
          this.trackWebVitals({
            name: 'CLS',
            value: clsValue,
            rating: clsValue <= 0.1 ? 'good' : clsValue <= 0.25 ? 'needs-improvement' : 'poor',
            id: `cls-${Date.now()}`,
          });
        }
      });

      try {
        clsObserver.observe({ entryTypes: ['layout-shift'] });
        this.webVitalsObserver = clsObserver;
      } catch (error) {
        console.warn('Layout shift observation not supported', error);
      }
    }
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
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

  private getPerformanceAttributes(): Record<string, number | string> {
    const attributes: Record<string, number | string> = {};

    try {
      if ('performance' in window) {
        const perf = performance as ExtendedPerformance;
        if (perf.memory) {
          attributes['browser.memory.used'] = perf.memory.usedJSHeapSize || 0;
          attributes['browser.memory.total'] = perf.memory.totalJSHeapSize || 0;
          attributes['browser.memory.limit'] = perf.memory.jsHeapSizeLimit || 0;
        }
      }

      const navigatorWithConnection = navigator as Navigator & { connection?: NavigatorConnection };
      const connection = navigatorWithConnection.connection;
      if (connection) {
        attributes['network.effective_type'] = connection.effectiveType || 'unknown';
        attributes['network.downlink'] = connection.downlink || 0;
        attributes['network.rtt'] = connection.rtt || 0;
      }
    } catch (error) {
      console.warn('Failed to get performance attributes:', error);
    }

    return attributes;
  }

  private getBrowserName(): string {
    const userAgent = navigator.userAgent;
    if (userAgent.includes('Chrome') && !userAgent.includes('Edge')) return 'chrome';
    if (userAgent.includes('Firefox')) return 'firefox';
    if (userAgent.includes('Safari') && !userAgent.includes('Chrome')) return 'safari';
    if (userAgent.includes('Edge')) return 'edge';
    if (userAgent.includes('Opera')) return 'opera';
    return 'unknown';
  }

  private getBrowserVersion(): string {
    const userAgent = navigator.userAgent;
    const match = userAgent.match(/(Chrome|Firefox|Safari|Edge|Opera)\/(\d+\.\d+)/);
    return match ? match[2] : 'unknown';
  }

  private getNavigationType(): string {
    try {
      const navigation = (window as Window & { navigation?: WindowNavigation }).navigation;
      if (navigation?.type) {
        return String(navigation.type);
      }
      if ('performance' in window) {
        const perf = performance as ExtendedPerformance;
        const legacyNavigation = perf.navigation;
        if (!legacyNavigation) {
          return 'unknown';
        }
        const type = legacyNavigation.type;
        switch (type) {
          case 0:
            return 'navigate';
          case 1:
            return 'reload';
          case 2:
            return 'back_forward';
          default:
            return 'unknown';
        }
      }
    } catch (error) {
      console.warn('Failed to get navigation type:', error);
    }
    return 'unknown';
  }

  private getPageLoadTime(): number {
    try {
      if ('performance' in window) {
        const perf = performance as ExtendedPerformance;
        if (perf.timing) {
          const timing = perf.timing;
          return timing.loadEventEnd - timing.navigationStart;
        }
      }
    } catch (error) {
      console.warn('Failed to get page load time:', error);
    }
    return 0;
  }

  private extractApiEndpoint(url: string): string {
    try {
      const urlObj = new URL(url);
      const pathParts = urlObj.pathname.split('/').filter(Boolean);
      if (pathParts.length >= 2 && pathParts[0] === 'api' && pathParts[1] === 'StoredProcedure') {
        return pathParts[2] || 'unknown';
      }
      return pathParts.join('/');
    } catch {
      return 'unknown';
    }
  }

  // Unused helper methods kept for potential future use (prefixed with _ to indicate intentionally unused)
  // @ts-expect-error - Intentionally unused, kept for potential future use
  private _enrichRequestSpan(span: Span, request: unknown): void {
    if (!this.userContext) return;

    // Add user context to requests
    span.setAttributes(this.getUserAttributes());

    // Add request details
    if (typeof request === 'string') {
      span.setAttributes({ 'http.url': request });
    } else if (request && typeof request === 'object') {
      const requestLike = request as { url?: string; method?: string };
      if (requestLike.url) {
        span.setAttributes({ 'http.url': requestLike.url });
      }
      if (requestLike.method) {
        span.setAttributes({ 'http.method': requestLike.method });
      }
    }
  }

  // @ts-expect-error - Intentionally unused, kept for potential future use
  private _enrichResponseSpan(span: Span, response: unknown): void {
    if (response && typeof response === 'object') {
      const responseLike = response as { status?: number; ok?: boolean };
      if (typeof responseLike.status === 'number') {
        span.setAttributes({
          'http.status_code': responseLike.status,
          'http.success': responseLike.status >= 200 && responseLike.status < 400,
        });
      }

      if (responseLike.ok === false && typeof responseLike.status === 'number') {
        span.setStatus({ code: 2, message: `HTTP ${responseLike.status}` });
      }
    }
  }
}

// Create singleton instance
export const telemetryService = new TelemetryService();

// Export configuration helper with improved defaults
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
    enabledInDevelopment: true, // Enable in dev for testing
    samplingRate: isDev ? 1.0 : 0.1, // 100% in dev, 10% in prod
    userConsent: true, // TODO: Implement proper consent management
    enableAutoInstrumentation: true,
    enableWebVitals: true,
  };
};

export default telemetryService;
