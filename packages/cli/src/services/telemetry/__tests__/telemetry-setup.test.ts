/**
 * The OTLP exporters the shipped CLI wires in setupOtelSdk, driven against a local collector. A dependency bump
 * (exporter-logs-otlp-http 0.301, sdk-logs and sdk-metrics 3.1) is only proven when a trace, a log record and a
 * metric each reach /v1/<signal> over the real exporters.
 */
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { SeverityNumber } from '@opentelemetry/api';
import { afterEach, describe, expect, it } from 'vitest';
import { setupOtelSdk } from '../telemetry-setup.js';

let server: Server | undefined;

afterEach(async () => {
  await new Promise<void>((resolve) => {
    if (!server) return resolve();
    server.close(() => resolve());
    server.closeAllConnections();
  });
  server = undefined;
});

async function collector(): Promise<{
  endpoint: string;
  paths: string[];
  bodies: Map<string, string>;
}> {
  const paths: string[] = [];
  const bodies = new Map<string, string>();
  server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => chunks.push(chunk));
    req.on('end', () => {
      paths.push(req.url ?? '');
      bodies.set(req.url ?? '', Buffer.concat(chunks).toString('latin1'));
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end('{}');
    });
  });
  await new Promise<void>((resolve) => server?.listen(0, '127.0.0.1', resolve));
  const { port } = server.address() as AddressInfo;
  return { endpoint: `http://127.0.0.1:${port}`, paths, bodies };
}

describe('setupOtelSdk against a local collector', () => {
  it('delivers a span, a log record and a metric to the OTLP http endpoints', async () => {
    const { endpoint, paths, bodies } = await collector();
    const setup = setupOtelSdk({
      endpoint,
      serviceName: 'rdc-test',
      serviceVersion: '0.0.0-dev',
      environment: 'test',
      headers: {},
      sessionId: 'session-test',
    });

    setup.tracer.startSpan('smoke').end();
    setup.logger.emit({ severityNumber: SeverityNumber.INFO, body: 'smoke' });
    setup.commandCounter.add(1);
    await setup.metricReader.forceFlush();
    await setup.sdk.shutdown();

    expect(paths).toContain('/v1/traces');
    expect(paths).toContain('/v1/logs');
    expect(paths).toContain('/v1/metrics');
    // The payload carries what was emitted, so an empty or wrong body to a path still fails.
    expect(bodies.get('/v1/logs')).toContain('smoke');
    expect(bodies.get('/v1/traces')).toContain('smoke');
  });
});
