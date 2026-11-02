// CLI Telemetry Service (OTel → Tempo/Prometheus/Loki via Alloy).
//
// Credentials are fetched at runtime from the account server's `/telemetry/config` endpoint (unauthenticated), set via `setRuntimeOtlpCredentials()`, and used when constructing the OTel SDK exporter. No credentials are ever baked into the bundle.
//
// Opt-out: `REDIACC_TELEMETRY_DISABLED=1` or any truthy `CI` env var.
// Use `isTelemetryDisabled()` (exported below) to check the state before doing any telemetry-related work, fetching credentials, spawning renet
// with OTLP env vars, or constructing an exporter. All three should skip
// when this returns true.

import { metrics as metricsApi, type Span, SpanStatusCode, type Tracer } from '@opentelemetry/api';
import { type Logger, SeverityNumber } from '@opentelemetry/api-logs';
import { type PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { type NodeSDK } from '@opentelemetry/sdk-node';
import { DEFAULTS, UPDATE_DEFAULTS } from '@rediacc/shared/config';
import type { TelemetryConfig, UserContext } from '@rediacc/shared/telemetry';
import {
  anonymizeArgs,
  anonymizeObject,
  errorToAttributes,
  generateSessionId,
} from '@rediacc/shared/telemetry';

import { isDevBuild } from '../../utils/platform.js';
import { VERSION as CLI_VERSION } from '../../version.js';
import { readAccountPointer } from '../account/account-pointer.js';
import {
  startProfiling as startProfilingImpl,
  stopProfiling as stopProfilingImpl,
} from './profiling.js';
import { currentRequestTelemetry } from './request-telemetry.js';
import { buildUserAttributes, flattenAttributes } from './telemetry-attrs.js';

/**
 * Pure env-var check for whether the user has opted out of telemetry.
 *
 * Callable before any service initialization, useful for gating
 * preAction work (credential fetch) and SSH env injection so we never
 * leak OTLP credentials to renet when the user has disabled telemetry
 * on their workstation.
 *
 * Disabled when:
 *   - `CI` env var is truthy (auto-disable in CI pipelines)
 *   - `REDIACC_TELEMETRY_DISABLED` is exactly `'1'` (explicit opt-out)
 */
export function isTelemetryDisabled(): boolean {
  return !!process.env.CI || process.env.REDIACC_TELEMETRY_DISABLED === '1';
}

export interface TelemetryInitConfig extends Partial<TelemetryConfig> {
  /** CLI-specific: telemetry enabled (default: true, opt-out) */
  telemetryEnabled?: boolean;
  /** Reported as `rediacc.region` on the resource. Set by the container executor. */
  region?: string;
}
type CliTelemetryConfig = TelemetryInitConfig;

interface CommandTrackingOptions {
  args?: string[];
  options?: Record<string, unknown>;
  /**
   * Key of the span in the active set. Defaults to the command name, which is only
   * unique in a process that runs one command at a time; the executor passes a
   * per-request key so two concurrent `repo list` spans do not overwrite each other.
   */
  spanKey?: string;
}
class CliTelemetryService {
  private sdk: NodeSDK | null = null;
  private tracer: Tracer | null = null;
  private logger: Logger | null = null;
  private metricReader: PeriodicExportingMetricReader | null = null;
  private isEnabled = true as boolean;
  private isInitialized = false as boolean;
  private profilingStarted = false as boolean;
  private readonly sessionId: string;
  private userContext: Partial<UserContext> = {};
  private readonly activeSpans: Map<string, Span> = new Map();
  private pendingShutdown: Promise<void> | null = null;
  /**
   * OTLP basic-auth token (base64-encoded `user:pass`), set by
   * `setRuntimeOtlpCredentials()` after the CLI fetches credentials from
   * `/telemetry/config`. Null means "no credentials for this region"
   * (bench, on-premise, or region with telemetry disabled): telemetry
   * stays disabled.
   */
  private authToken: string | null = null;

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
    // Env-based opt-out (CI, REDIACC_TELEMETRY_DISABLED) is the single source of truth, see `isTelemetryDisabled()` at module scope. The in-memory `config.telemetryEnabled` override is an additional layer used by adapters that want to force-disable for a specific context.
    if (isTelemetryDisabled()) return true;
    if (config?.telemetryEnabled === false) return true;
    return false;
  }

  /**
   * Provide OTLP credentials fetched from the account server. Must be
   * called before `initialize()` so the OTel SDK exporter is constructed
   * with the correct auth header. Passing `null` clears any previously
   * set credentials; subsequent `initialize()` calls will produce a
   * no-op collector (default-deny).
   */
  setRuntimeOtlpCredentials(creds: { user: string; pass: string } | null): void {
    if (creds?.user && creds.pass) {
      this.authToken = Buffer.from(`${creds.user}:${creds.pass}`).toString('base64');
    } else {
      this.authToken = null;
    }
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
    return isDevBuild() ? 'development' : DEFAULTS.TELEMETRY.ENVIRONMENT;
  }

  private getEndpoint(): string {
    // Allow endpoint override only in development
    if (this.detectEnvironment() === 'development' && process.env.REDIACC_TELEMETRY_ENDPOINT) {
      return process.env.REDIACC_TELEMETRY_ENDPOINT;
    }

    return 'https://otlp.rediacc.io';
  }

  private resolveUpdateChannel(): string {
    return (
      process.env.REDIACC_UPDATE_CHANNEL ??
      readAccountPointer().updateChannel ??
      UPDATE_DEFAULTS.CHANNEL
    );
  }

  private getExporterHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.authToken) {
      headers['Authorization'] = `Basic ${this.authToken}`;
    }
    return headers;
  }

  async initialize(config?: CliTelemetryConfig): Promise<void> {
    if (this.isInitialized) {
      return;
    }

    if (this.shouldDisable(config)) {
      this.isEnabled = false;
      this.isInitialized = true;
      return;
    }

    // Default-deny: without credentials we never construct the exporter, so no requests are sent and no metadata leaks. Matches renet's default-deny behavior and fixes the unauthenticated-request path
    // from renet#51.
    if (!this.authToken) {
      this.isEnabled = false;
      this.isInitialized = true;
      return;
    }

    try {
      // Lazy-load the OTel SDK factory graph (~1.8 MB of @opentelemetry modules). Only opted-in runs with credentials reach here, so --version/--help/opted-out invocations never execute it.
      const { setupOtelSdk } = await import('./telemetry-setup.js');
      const result = setupOtelSdk({
        endpoint: config?.endpoint ?? this.getEndpoint(),
        serviceName: config?.serviceName ?? DEFAULTS.TELEMETRY.SERVICE_NAME,
        serviceVersion: config?.serviceVersion ?? CLI_VERSION,
        environment: config?.environment ?? this.detectEnvironment(),
        updateChannel: this.resolveUpdateChannel(),
        headers: this.getExporterHeaders(),
        sessionId: this.sessionId,
        ...(config?.region ? { region: config.region } : {}),
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

  /** True while an SDK is constructed and exporting (not disabled, not credential-less). */
  isRunning(): boolean {
    return this.isEnabled && this.sdk !== null;
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

      this.activeSpans.set(options?.spanKey ?? commandName, span);

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
    result: { success: boolean; exitCode?: number; error?: string; duration?: number },
    spanKey: string = commandName
  ): void {
    if (!this.isEnabled) {
      return;
    }

    try {
      const span = this.activeSpans.get(spanKey);
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
      this.activeSpans.delete(spanKey);

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

  shutdown(): Promise<void> {
    if (!this.isEnabled || !this.sdk) {
      return Promise.resolve();
    }

    // Prevent multiple shutdown calls
    if (this.pendingShutdown !== null) {
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
    // Inside an executor request the user is the introspected caller. The singleton's context is the executor's own token and would attribute every caller's command to it.
    const scope = currentRequestTelemetry();
    if (scope) {
      const caller = scope.caller;
      if (!caller) return {};
      return {
        ...buildUserAttributes({ email: caller.userEmail, organization: caller.orgId }),
        'user.id': caller.userId,
      };
    }
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
