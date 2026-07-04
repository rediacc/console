import * as esbuild from 'esbuild';

/** Plugin to exclude native .node bindings from the bundle.
 *  ssh2 and cpu-features have optional native bindings wrapped in try/catch,
 *  so they gracefully fall back to pure JavaScript when unavailable. */
const nativeModulesPlugin = {
  name: 'native-node-modules',
  setup(build) {
    build.onResolve({ filter: /\.node$/ }, (args) => ({
      path: args.path,
      external: true,
    }));
  },
};

/**
 * Stub the grpc/proto OTLP exporters so their transitive graph
 * (@grpc/grpc-js ~670 KB, @grpc/proto-loader, protobufjs ~360 KB) never
 * enters the bundle.
 *
 * `@opentelemetry/sdk-node` top-level-requires all of these, but the CLI
 * always constructs explicit OTLP-HTTP exporters in
 * `services/telemetry/telemetry-setup.ts` and passes them to NodeSDK, so
 * sdk-node's env-based grpc/proto exporter selection is never reached.
 * The stub is a Proxy: reading any property returns a class that throws
 * only when constructed — so the eager top-level `require()`s in sdk-node
 * stay safe (they merely bind the module), and any accidental
 * construction fails loudly instead of silently sending to the wrong
 * transport.
 */
const STUBBED_GRPC_PROTO = [
  '@opentelemetry/exporter-trace-otlp-grpc',
  '@opentelemetry/exporter-logs-otlp-grpc',
  '@opentelemetry/exporter-metrics-otlp-grpc',
  '@opentelemetry/otlp-grpc-exporter-base',
  '@opentelemetry/exporter-trace-otlp-proto',
  '@opentelemetry/exporter-logs-otlp-proto',
  '@opentelemetry/exporter-metrics-otlp-proto',
];
const grpcProtoStubPlugin = {
  name: 'stub-grpc-proto-exporters',
  setup(build) {
    const escaped = STUBBED_GRPC_PROTO.map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const filter = new RegExp(`^(${escaped.join('|')})$`);
    build.onResolve({ filter }, (args) => ({ path: args.path, namespace: 'grpc-proto-stub' }));
    build.onLoad({ filter: /.*/, namespace: 'grpc-proto-stub' }, (args) => ({
      contents: `
        const message = ${JSON.stringify(
          `grpc/proto OTLP exporters are not bundled in rdc (OTLP-HTTP only): ${args.path}`
        )};
        module.exports = new Proxy(
          {},
          {
            get(target, prop) {
              // Thenable/symbol introspection (a loader probing '.then', or
              // Symbol.toStringTag / inspect) must not receive the throwing
              // class, or it gets called as a function and crashes at load.
              // Real exporter classes are string-named exports, which still
              // throw on construction.
              if (prop === 'then' || typeof prop === 'symbol') {
                return undefined;
              }
              return class {
                constructor() {
                  throw new Error(message);
                }
              };
            },
          }
        );
      `,
      loader: 'js',
    }));
  },
};

const result = await esbuild.build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  platform: 'node',
  target: 'node18',
  outfile: 'dist/cli-bundle.cjs',
  format: 'cjs',
  // Note: shebang comes from src/index.ts - no banner needed
  external: [],
  plugins: [grpcProtoStubPlugin, nativeModulesPlugin],
  logLevel: 'silent',
  define: {
    '__CLI_VERSION__': JSON.stringify(process.env.CLI_VERSION || '0.0.0-dev'),
  },
});

if (result.warnings.length > 0) {
  const formattedWarnings = await esbuild.formatMessages(result.warnings, {
    kind: 'warning',
    color: true,
  });
  for (const warning of formattedWarnings) {
    console.error(warning);
  }
  process.exit(1);
}

console.log('✓ CLI bundled to dist/cli-bundle.cjs');
