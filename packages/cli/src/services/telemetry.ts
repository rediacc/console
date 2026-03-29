// CLI Telemetry Service (OTel → Tempo/Prometheus/Loki via Alloy). Opt-out: REDIACC_TELEMETRY_DISABLED=1

/** Injected at compile time by esbuild (see bundle.mjs). */
declare const __OTLP_AUTH_TOKEN__: string;

import { metrics as metricsApi, type Span, SpanStatusCode, type Tracer } from '@opentelemetry/api';
import { type Logger, SeverityNumber } from '@opentelemetry/api-logs';
import { type PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { type NodeSDK } from '@opentelemetry/sdk-node';
import type { TelemetryConfig, TelemetryHandler, UserContext } from '@rediacc/shared/api';
import { DEFAULTS, UPDATE_DEFAULTS } from '@rediacc/shared/config';
import {
  anonymizeArgs,
  anonymizeObject,
  errorToAttributes,
  extractApiEndpoint,
  generateSessionId,
} from '@rediacc/shared/telemetry';

import { buildUserAttributes, flattenAttributes } from './telemetry-attrs.js';
import { setupOtelSdk } from './telemetry-setup.js';

import {
  startProfiling as startProfilingImpl,
  stopProfiling as stopProfilingImpl,
} from './profiling.js';

// Package version (will be replaced by bundler or read from package.json)
const CLI_VERSION = '0.3.6';

interface CliTelemetryConfig extends Partial<TelemetryConfig> {
  /** CLI-specific: telemetry enabled (default: true, opt-out) */
  telemetryEnabled?: boolean;
}

interface CommandTrackingOptions {
  args?: string[];
  options?: Record<string, unknown>;
}
class CliTelemetryService implements TelemetryHandler {
  private sdk: NodeSDK | null = null;
  private tracer: Tracer | null = null;
  private logger: Logger | null = null;
  private metricReader: PeriodicExportingMetricReader | null = null;
  private isEnabled = true;
  private isInitialized = false;
  private profilingStarted = false;
  private readonly sessionId: string;
  private userContext: Partial<UserContext> = {};
  private readonly activeSpans: Map<string, Span> = new Map();
  private pendingShutdown: Promise<void> | null = null;

  // Metrics instruments
  private commandCounter: ReturnType<
    ReturnType<typeof metricsApi.getMeter>['createCounter']
  > | null = null;
  private commandDuration: ReturnType<
    ReturnType<typeof metricsApi.getMeter>['createHistogram']
  > | null = null;
  private errorCounter: ReturnType<ReturnType<typeof metricsApi.getMeter>['createCounter']> | null =
    null;
  private apiCallDuration: ReturnType<
    ReturnType<typeof metricsApi.getMeter>['createHistogram']
  > | null = null;

  constructor() {
    this.sessionId = generateSessionId();
  }

  private shouldDisable(config?: CliTelemetryConfig): boolean {
    // Disable in CI environments to avoid delays in automated pipelines
    if (process.env.CI) {
      return true;
    }

    // Check environment variable
    if (process.env.REDIACC_TELEMETRY_DISABLED === '1') {
      return true;
    }

    // Check config
    if (config?.telemetryEnabled === false) {
      return true;
    }

    return false;
  }

  private getAuthToken(): string | null {
    // Production: embedded at compile time by esbuild define (non-overridable)
    const embedded = typeof __OTLP_AUTH_TOKEN__ !== 'undefined' && __OTLP_AUTH_TOKEN__;
    if (embedded) return embedded;
    // Development: rdc.sh sources account .env which sets this
    if (this.detectEnvironment() === 'development') {
      return process.env.REDIACC_TELEMETRY_AUTH_TOKEN ?? null;
    }
    return null;
  }

  private detectEnvironment(): string {
    // Running via tsx or ts-node means dev mode (./rdc.sh)
    const execArgs = process.execArgv.join(' ');
    if (
      execArgs.includes('tsx') ||
      execArgs.includes('ts-node') ||
      process.argv[1]?.endsWith('.ts')
    ) {
      return 'development';
    }
    return DEFAULTS.TELEMETRY.ENVIRONMENT;
  }

  private getEndpoint(): string {
    // Allow endpoint override only in development
    if (this.detectEnvironment() === 'development' && process.env.REDIACC_TELEMETRY_ENDPOINT) {
      return process.env.REDIACC_TELEMETRY_ENDPOINT;
    }

    return 'https://otlp.rediacc.io';
  }

  private resolveUpdateChannel(): string {
    // Read channel from env (avoids circular/dynamic imports).
    // server.json channel is resolved later by the updater; for telemetry
    // resource attributes, env var is sufficient since it's set at startup.
    const envChannel = process.env.RDC_UPDATE_CHANNEL;
    if (envChannel === 'edge' || envChannel === 'stable') return envChannel;
    return UPDATE_DEFAULTS.CHANNEL;
  }

  private getExporterHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    const authToken = this.getAuthToken();
    if (authToken) {
      headers['Authorization'] = `Basic ${authToken}`;
    }
    return headers;
  }

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
      const result = setupOtelSdk({
        endpoint: config?.endpoint ?? this.getEndpoint(),
        serviceName: config?.serviceName ?? DEFAULTS.TELEMETRY.SERVICE_NAME,
        serviceVersion: config?.serviceVersion ?? CLI_VERSION,
        environment:
          config?.environment ?? process.env.REDIACC_ENVIRONMENT ?? this.detectEnvironment(),
        updateChannel: this.resolveUpdateChannel(),
        headers: this.getExporterHeaders(),
        sessionId: this.sessionId,
      });

      this.sdk = result.sdk;
      this.tracer = result.tracer;
      this.logger = result.logger;
      this.metricReader = result.metricReader;
      this.commandCounter = result.commandCounter;
      this.commandDuration = result.commandDuration;
      this.errorCounter = result.errorCounter;
      this.apiCallDuration = result.apiCallDuration;
      this.isInitialized = true;
    } catch {
      this.isEnabled = false;
      this.isInitialized = true;
    }
  }

  startProfiling(commandName: string): void {
    if (!this.isEnabled || this.profilingStarted) {
      return;
    }
    startProfilingImpl(commandName);
    this.profilingStarted = true;
  }

  async stopProfiling(): Promise<void> {
    if (!this.profilingStarted) {
      return;
    }
    await stopProfilingImpl();
  }

  setUserContext(context: Partial<UserContext>): void {
    this.userContext = {
      ...this.userContext,
      ...context,
      sessionId: this.sessionId,
    };
  }

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

      // Log command start
      this.emitLog(SeverityNumber.INFO, `Command started: ${commandName}`, {
        'cli.command': commandName,
        'cli.version': CLI_VERSION,
      });
    } catch {
      // Fail silently
    }
  }

  private buildCommandLogAttrs(
    commandName: string,
    result: { success: boolean; exitCode?: number; error?: string; duration?: number }
  ): Record<string, unknown> {
    const attrs: Record<string, unknown> = {
      'cli.command': commandName,
      'cli.success': result.success,
      'cli.exit_code': result.exitCode ?? (result.success ? 0 : 1),
    };
    if (result.error) {
      attrs['cli.error'] = result.error;
    }
    if (result.duration !== undefined) {
      attrs['cli.duration_ms'] = result.duration;
    }
    return attrs;
  }

  endCommand(
    commandName: string,
    result: { success: boolean; exitCode?: number; error?: string; duration?: number }
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

      // Record metrics
      const attrs = { 'cli.command': commandName, 'cli.success': result.success };
      this.commandCounter?.add(1, attrs);
      if (result.duration !== undefined) {
        this.commandDuration?.record(result.duration, attrs);
      }

      // Log command completion
      const severity = result.success ? SeverityNumber.INFO : SeverityNumber.ERROR;
      const label = result.success ? 'completed' : 'failed';
      this.emitLog(
        severity,
        `Command ${label}: ${commandName}`,
        this.buildCommandLogAttrs(commandName, result)
      );
    } catch {
      // Fail silently
    }
  }

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

      // Record API metrics
      this.apiCallDuration?.record(duration, {
        'http.method': method.toUpperCase(),
        'api.endpoint': endpoint,
        'http.status_code': status ?? 0,
      });
    } catch {
      // Fail silently
    }
  }

  trackError(error: unknown, context?: Record<string, unknown>): void {
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

      // Record error metric
      this.errorCounter?.add(1, {
        'error.type': errorAttrs['error.type'],
      });

      // Log error to Loki
      this.emitLog(SeverityNumber.ERROR, errorAttrs['error.message'], {
        ...errorAttrs,
        ...this.flattenAttributes(safeContext),
      });
    } catch {
      // Fail silently
    }
  }

  trackMetric(name: string, value: number, unit?: string): void {
    if (!this.isEnabled || !this.tracer) {
      return;
    }

    try {
      // Record as a trace span for correlation
      const span = this.tracer.startSpan('cli.metric');

      span.setAttributes({
        'metric.name': name,
        'metric.value': value,
        'metric.unit': unit ?? DEFAULTS.TELEMETRY.UNIT,
        'session.id': this.sessionId,
      });

      span.setStatus({ code: SpanStatusCode.OK });
      span.end();
    } catch {
      // Fail silently
    }
  }

  private emitLog(
    severity: SeverityNumber,
    message: string,
    attributes?: Record<string, unknown>
  ): void {
    if (!this.logger) {
      return;
    }

    try {
      this.logger.emit({
        severityNumber: severity,
        severityText: this.severityToText(severity),
        body: message,
        attributes: {
          'session.id': this.sessionId,
          ...this.getUserAttributes(),
          ...attributes,
        },
      });
    } catch {
      // Fail silently
    }
  }

  private severityToText(severity: SeverityNumber): string {
    if (severity <= SeverityNumber.DEBUG4) return 'DEBUG';
    if (severity <= SeverityNumber.INFO4) return 'INFO';
    if (severity <= SeverityNumber.WARN4) return 'WARN';
    return 'ERROR';
  }

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

        // Force-flush metrics before SDK shutdown (CLI is short-lived)
        await Promise.race([
          this.metricReader?.forceFlush(),
          new Promise((resolve) => {
            const t = setTimeout(resolve, 3000);
            if (typeof t === 'object' && 'unref' in t) t.unref();
          }),
        ]);

        // Shutdown SDK with timeout to avoid delaying CLI exit
        await Promise.race([
          this.sdk?.shutdown(),
          new Promise((resolve) => {
            const t = setTimeout(resolve, 3000);
            if (typeof t === 'object' && 'unref' in t) t.unref();
          }),
        ]);
      } catch {
        // Fail silently
      }
    })();

    return this.pendingShutdown;
  }

  private getUserAttributes(): Record<string, string> {
    return buildUserAttributes(this.userContext);
  }

  private flattenAttributes(
    obj: Record<string, unknown>,
    prefix = ''
  ): Record<string, string | number | boolean> {
    return flattenAttributes(obj, prefix);
  }
}

// Export singleton instance
export const telemetryService = new CliTelemetryService();
