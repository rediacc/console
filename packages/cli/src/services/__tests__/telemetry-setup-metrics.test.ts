import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, describe, expect, it } from 'vitest';
import { setupOtelSdk } from '../telemetry/telemetry-setup.js';

// OpenTelemetry JS 3 replaced NodeSDK's `metricReader` with `metricReaders: [...]`. tsc checks the option's name and type, not that
// the reader is bound to the meter provider, so this drives the real SDK against a local collector and requires a metrics export.
describe('setupOtelSdk metrics wiring', () => {
  let server: Server | undefined;
  let shutdown: (() => Promise<void>) | undefined;

  afterEach(async () => {
    try {
      await shutdown?.();
    } finally {
      // Closed even when shutdown rejects, so a failing run does not leak a listening server into later tests.
      await new Promise<void>((resolve) => (server ? server.close(() => resolve()) : resolve()));
      server = undefined;
      shutdown = undefined;
    }
  });

  it('exports a recorded counter to /v1/metrics on a reader flush', async () => {
    const metricBodies: Buffer[] = [];
    server = createServer((req, res) => {
      const chunks: Buffer[] = [];
      req.on('data', (c: Buffer) => chunks.push(c));
      req.on('end', () => {
        if (req.url === '/v1/metrics') metricBodies.push(Buffer.concat(chunks));
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end('{}');
      });
    });
    await new Promise<void>((resolve) => server?.listen(0, '127.0.0.1', resolve));
    const { port } = server.address() as AddressInfo;

    const otel = setupOtelSdk({
      endpoint: `http://127.0.0.1:${port}`,
      serviceName: 'rdc-test',
      serviceVersion: '0.0.0-test',
      environment: 'test',
      headers: {},
      sessionId: 'test-session',
    });
    shutdown = () => otel.sdk.shutdown();

    otel.commandCounter.add(1, { command: 'test' });
    await otel.metricReader.forceFlush();

    // The instrument's name is plain bytes in both the JSON and the protobuf encodings, so this ties the export to THIS counter.
    expect(metricBodies.some((b) => b.includes('cli.command.count'))).toBe(true);
  });
});
