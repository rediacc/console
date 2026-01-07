/**
 * CLI Telemetry Service
 *
 * Provides OpenTelemetry-based telemetry for CLI commands.
 * Tracks command execution, API calls, and errors.
 *
 * Opt-out: Set REDIACC_TELEMETRY=off to disable telemetry.
 */

import { trace, SpanStatusCode, type Span, type Tracer } from '@opentelemetry/api';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';
import type { TelemetryConfig, TelemetryHandler, UserContext } from '@rediacc/shared/api';
import {
  generateSessionId,
  anonymizeObject,
  anonymizeArgs,
  errorToAttributes,
  extractApiEndpoint,
} from '@rediacc/shared/telemetry';

// Package version (will be replaced by bundler or read from package.json)
const CLI_VERSION = '0.3.6';

/**
 * Configuration for CLI telemetry.
 */
interface CliTelemetryConfig extends Partial<TelemetryConfig> {
  /** CLI-specific: telemetry enabled (default: true, opt-out) */
  telemetryEnabled?: boolean;
}

/**
 * Options for command tracking.
 */
interface CommandTrackingOptions {
  args?: string[];
  options?: Record<string, unknown>;
}

/**
 * CLI Telemetry Service implementation.
 */
class CliTelemetryService implements TelemetryHandler {
  private sdk: NodeSDK | null = null;
  private tracer: Tracer | null = null;
  private isEnabled = true;
  private isInitialized = false;
  private sessionId: string;
  private userContext: Partial<UserContext> = {};
  private activeSpans: Map<string, Span> = new Map();
  private pendingShutdown: Promise<void> | null = null;

  constructor() {
    this.sessionId = generateSessionId();
  }

  /**
   * Check if telemetry is disabled via environment variable or config.
   */
  private shouldDisable(config?: CliTelemetryConfig): boolean {
    // Check environment variable first
    const envValue = process.env.REDIACC_TELEMETRY?.toLowerCase();
    if (envValue === 'off' || envValue === 'false' || envValue === '0') {
      return true;
    }

    // Check config
    if (config?.telemetryEnabled === false) {
      return true;
    }

    return false;
  }

  /**
   * Get the telemetry endpoint based on environment.
   */
  private getEndpoint(): string {
    // Use environment variable if set
    if (process.env.REDIACC_TELEMETRY_ENDPOINT) {
      return process.env.REDIACC_TELEMETRY_ENDPOINT;
    }

    // Default to production endpoint
    return 'https://www.rediacc.com/otlp';
  }

  /**
   * Initialize the telemetry service.
   */
  initialize(config?: CliTelemetryConfig): void {
    if (this.isInitialized) {
      return;
    }

    if (this.shouldDisable(config)) {
      this.isEnabled = false;
      this.isInitialized = true;
      return;
    }

    try {
      const endpoint = config?.endpoint ?? this.getEndpoint();
      const serviceName = config?.serviceName ?? 'rediacc-cli';
      const serviceVersion = config?.serviceVersion ?? CLI_VERSION;
      const environment = config?.environment ?? 'production';

      const resource = new Resource({
        [ATTR_SERVICE_NAME]: serviceName,
        [ATTR_SERVICE_VERSION]: serviceVersion,
        'deployment.environment': environment,
        'service.platform': 'cli',
        'os.type': process.platform,
        'runtime.name': 'nodejs',
        'runtime.version': process.version,
        'session.id': this.sessionId,
      });

      const exporter = new OTLPTraceExporter({
        url: `${endpoint}/v1/traces`,
        headers: { 'Content-Type': 'application/json' },
        timeoutMillis: 5000, // Short timeout to not block CLI
      });

      this.sdk = new NodeSDK({
        resource,
        traceExporter: exporter,
      });

      this.sdk.start();
      this.tracer = trace.getTracer(serviceName, serviceVersion);
      this.isInitialized = true;
    } catch {
      // Fail silently - telemetry should never break the CLI
      this.isEnabled = false;
      this.isInitialized = true;
    }
  }

  /**
   * Set user context for telemetry attribution.
   */
  setUserContext(context: Partial<UserContext>): void {
    this.userContext = {
      ...this.userContext,
      ...context,
      sessionId: this.sessionId,
    };
  }

  /**
   * Track a generic event.
   */
  trackEvent(eventName: string, attributes?: Record<string, unknown>): void {
    if (!this.isEnabled || !this.tracer) {
      return;
    }

    try {
      const span = this.tracer.startSpan(eventName);
      const safeAttributes = attributes ? anonymizeObject(attributes) : {};

      span.setAttributes({
        'event.name': eventName,
        'event.timestamp': Date.now(),
        'session.id': this.sessionId,
        ...this.getUserAttributes(),
        ...this.flattenAttributes(safeAttributes),
      });

      span.setStatus({ code: SpanStatusCode.OK });
      span.end();
    } catch {
      // Fail silently
    }
  }

  /**
   * Start tracking a command execution.
   */
  startCommand(commandName: string, options?: CommandTrackingOptions): void {
    if (!this.isEnabled || !this.tracer) {
      return;
    }

    try {
      const span = this.tracer.startSpan(`cli.command.${commandName}`);

      const safeArgs = options?.args ? anonymizeArgs(options.args) : [];
      const safeOptions = options?.options ? anonymizeObject(options.options) : {};

      span.setAttributes({
        'cli.command': commandName,
        'cli.args': JSON.stringify(safeArgs),
        'cli.options': JSON.stringify(safeOptions),
        'cli.version': CLI_VERSION,
        'session.id': this.sessionId,
        ...this.getUserAttributes(),
      });

      this.activeSpans.set(commandName, span);
    } catch {
      // Fail silently
    }
  }

  /**
   * End tracking a command execution.
   */
  endCommand(
    commandName: string,
    result: { success: boolean; exitCode?: number; error?: string }
  ): void {
    if (!this.isEnabled) {
      return;
    }

    try {
      const span = this.activeSpans.get(commandName);
      if (!span) {
        return;
      }

      span.setAttributes({
        'cli.success': result.success,
        'cli.exit_code': result.exitCode ?? (result.success ? 0 : 1),
      });

      if (result.error) {
        span.setAttributes({ 'cli.error': result.error });
        span.setStatus({ code: SpanStatusCode.ERROR, message: result.error });
      } else {
        span.setStatus({ code: SpanStatusCode.OK });
      }

      span.end();
      this.activeSpans.delete(commandName);
    } catch {
      // Fail silently
    }
  }

  /**
   * Track an API call (required by TelemetryHandler interface).
   */
  trackApiCall(
    method: string,
    url: string,
    status: number | undefined,
    duration: number,
    error?: string
  ): void {
    if (!this.isEnabled || !this.tracer) {
      return;
    }

    try {
      const span = this.tracer.startSpan('cli.api.call');
      const endpoint = extractApiEndpoint(url);

      span.setAttributes({
        'http.method': method.toUpperCase(),
        'http.url': url,
        'http.status_code': status ?? 0,
        'http.duration_ms': duration,
        'api.endpoint': endpoint,
        'session.id': this.sessionId,
        ...this.getUserAttributes(),
      });

      if (error) {
        span.setAttributes({ 'http.error': error });
        span.setStatus({ code: SpanStatusCode.ERROR, message: error });
      } else {
        span.setStatus({ code: SpanStatusCode.OK });
      }

      span.end();
    } catch {
      // Fail silently
    }
  }

  /**
   * Track an error.
   */
  trackError(error: Error | unknown, context?: Record<string, unknown>): void {
    if (!this.isEnabled || !this.tracer) {
      return;
    }

    try {
      const span = this.tracer.startSpan('cli.error');
      const errorAttrs = errorToAttributes(error);
      const safeContext = context ? anonymizeObject(context) : {};

      span.setAttributes({
        ...errorAttrs,
        'session.id': this.sessionId,
        ...this.getUserAttributes(),
        ...this.flattenAttributes(safeContext),
      });

      span.setStatus({
        code: SpanStatusCode.ERROR,
        message: errorAttrs['error.message'],
      });

      span.end();
    } catch {
      // Fail silently
    }
  }

  /**
   * Track a performance metric.
   */
  trackMetric(name: string, value: number, unit?: string): void {
    if (!this.isEnabled || !this.tracer) {
      return;
    }

    try {
      const span = this.tracer.startSpan('cli.metric');

      span.setAttributes({
        'metric.name': name,
        'metric.value': value,
        'metric.unit': unit ?? 'ms',
        'session.id': this.sessionId,
      });

      span.setStatus({ code: SpanStatusCode.OK });
      span.end();
    } catch {
      // Fail silently
    }
  }

  /**
   * Shutdown telemetry and flush pending data.
   */
  async shutdown(): Promise<void> {
    if (!this.isEnabled || !this.sdk) {
      return;
    }

    // Prevent multiple shutdown calls
    if (this.pendingShutdown) {
      return this.pendingShutdown;
    }

    this.pendingShutdown = (async () => {
      try {
        // End any active spans
        for (const [name, span] of this.activeSpans) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'CLI shutdown' });
          span.end();
          this.activeSpans.delete(name);
        }

        // Shutdown SDK with timeout
        await Promise.race([
          this.sdk?.shutdown(),
          new Promise((resolve) => setTimeout(resolve, 3000)),
        ]);
      } catch {
        // Fail silently
      }
    })();

    return this.pendingShutdown;
  }

  /**
   * Get user attributes for telemetry.
   */
  private getUserAttributes(): Record<string, string> {
    const attrs: Record<string, string> = {};

    if (this.userContext.email) {
      // Only include email domain for privacy
      const domain = this.userContext.email.split('@')[1];
      if (domain) {
        attrs['user.email_domain'] = domain;
      }
    }

    if (this.userContext.organization) {
      attrs['user.organization'] = this.userContext.organization;
    }

    if (this.userContext.teamName) {
      attrs['user.team'] = this.userContext.teamName;
    }

    return attrs;
  }

  /**
   * Flatten nested objects to dot-notation keys.
   */
  private flattenAttributes(
    obj: Record<string, unknown>,
    prefix = ''
  ): Record<string, string | number | boolean> {
    const result: Record<string, string | number | boolean> = {};

    for (const [key, value] of Object.entries(obj)) {
      const fullKey = prefix ? `${prefix}.${key}` : key;

      if (value === null || value === undefined) {
        continue;
      } else if (typeof value === 'object' && !Array.isArray(value)) {
        Object.assign(result, this.flattenAttributes(value as Record<string, unknown>, fullKey));
      } else if (
        typeof value === 'string' ||
        typeof value === 'number' ||
        typeof value === 'boolean'
      ) {
        result[fullKey] = value;
      } else {
        result[fullKey] = String(value);
      }
    }

    return result;
  }
}

// Export singleton instance
export const telemetryService = new CliTelemetryService();
