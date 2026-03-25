import { diag, DiagLogLevel, metrics as metricsApi, trace } from '@opentelemetry/api';
import { type Logger, logs } from '@opentelemetry/api-logs';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { SimpleLogRecordProcessor } from '@opentelemetry/sdk-logs';
import { AggregationTemporality, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';

export interface SdkSetupResult {
  sdk: NodeSDK;
  tracer: ReturnType<typeof trace.getTracer>;
  logger: Logger;
  metricReader: PeriodicExportingMetricReader;
  commandCounter: ReturnType<ReturnType<typeof metricsApi.getMeter>['createCounter']>;
  commandDuration: ReturnType<ReturnType<typeof metricsApi.getMeter>['createHistogram']>;
  errorCounter: ReturnType<ReturnType<typeof metricsApi.getMeter>['createCounter']>;
  apiCallDuration: ReturnType<ReturnType<typeof metricsApi.getMeter>['createHistogram']>;
}

export function setupOtelSdk(opts: {
  endpoint: string;
  serviceName: string;
  serviceVersion: string;
  environment: string;
  headers: Record<string, string>;
  sessionId: string;
}): SdkSetupResult {
  // Suppress OTel SDK diagnostic output unless debug is requested.
  if (process.env.REDIACC_DEBUG !== '1') {
    diag.setLogger(
      { error() {}, warn() {}, info() {}, debug() {}, verbose() {} },
      DiagLogLevel.NONE
    );
  }

  const resource = resourceFromAttributes({
    [ATTR_SERVICE_NAME]: opts.serviceName,
    [ATTR_SERVICE_VERSION]: opts.serviceVersion,
    'deployment.environment': opts.environment,
    'service.platform': 'cli',
    'os.type': process.platform,
    'runtime.name': 'nodejs',
    'runtime.version': process.version,
    'session.id': opts.sessionId,
  });

  const traceExporter = new OTLPTraceExporter({
    url: `${opts.endpoint}/v1/traces`,
    headers: opts.headers,
    timeoutMillis: 5000,
  });

  const metricExporter = new OTLPMetricExporter({
    url: `${opts.endpoint}/v1/metrics`,
    headers: opts.headers,
    timeoutMillis: 5000,
    temporalityPreference: AggregationTemporality.CUMULATIVE,
  });

  const metricReader = new PeriodicExportingMetricReader({
    exporter: metricExporter,
    exportIntervalMillis: 60000,
  });

  const logExporter = new OTLPLogExporter({
    url: `${opts.endpoint}/v1/logs`,
    headers: opts.headers,
    timeoutMillis: 5000,
  });

  const sdk = new NodeSDK({
    resource,
    traceExporter,
    metricReader,
    logRecordProcessors: [new SimpleLogRecordProcessor(logExporter)],
  });

  sdk.start();

  const tracer = trace.getTracer(opts.serviceName, opts.serviceVersion);
  const logger = logs.getLogger(opts.serviceName, opts.serviceVersion);
  const meter = metricsApi.getMeter(opts.serviceName, opts.serviceVersion);

  return {
    sdk,
    tracer,
    logger,
    metricReader,
    commandCounter: meter.createCounter('cli.command.count', {
      description: 'Number of CLI commands executed',
    }),
    commandDuration: meter.createHistogram('cli.command.duration', {
      description: 'CLI command execution duration in ms',
      unit: 'ms',
    }),
    errorCounter: meter.createCounter('cli.error.count', {
      description: 'Number of CLI errors',
    }),
    apiCallDuration: meter.createHistogram('cli.api.duration', {
      description: 'CLI API call duration in ms',
      unit: 'ms',
    }),
  };
}
