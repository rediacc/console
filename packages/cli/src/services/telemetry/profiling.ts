/**
 * Profiling Service - Pyroscope continuous profiling for CLI.
 *
 * Lazy-loads @pyroscope/nodejs to avoid loading native modules when not needed.
 * Opt-out: Set REDIACC_TELEMETRY_DISABLED=1 to disable.
 */

import { createRequire } from 'node:module';
import { DEFAULTS } from '@rediacc/shared/config';

/** Minimal interface for @pyroscope/nodejs methods we use. */
interface PyroscopeModule {
  init(config: {
    appName: string;
    serverAddress: string;
    basicAuthUser: string;
    basicAuthPassword: string;
    tags: Record<string, string>;
  }): void;
  startCpuProfiling(): void;
  startHeapProfiling(): void;
  stopCpuProfiling(): Promise<void>;
  stopHeapProfiling(): Promise<void>;
}

/** Lazy-load @pyroscope/nodejs to avoid loading native module when not needed. */
let pyroscopeModule: PyroscopeModule | null | undefined;
function loadPyroscope(): PyroscopeModule | null {
  if (pyroscopeModule !== undefined) return pyroscopeModule;
  try {
    // Resolve require base: import.meta.url for ESM, __filename for CJS/bundled
    let requireBase: string | undefined;
    if (typeof import.meta.url === 'string') {
      requireBase = import.meta.url;
    } else if (typeof __filename === 'string') {
      requireBase = __filename;
    }
    if (!requireBase) {
      pyroscopeModule = null;
      return null;
    }
    const cjsRequire = createRequire(requireBase);
    const mod = cjsRequire('@pyroscope/nodejs');
    pyroscopeModule = (mod.default ?? mod) as PyroscopeModule;
    return pyroscopeModule;
  } catch {
    pyroscopeModule = null;
    return null;
  }
}

/**
 * Detect whether CLI is running in development (tsx) or production.
 */
function detectEnvironment(): string {
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

/**
 * Start CPU and heap profiling via Pyroscope.
 */
export function startProfiling(commandName: string, environment?: string): void {
  try {
    const pyroscope = loadPyroscope();
    if (!pyroscope) return;

    const env = environment ?? process.env.REDIACC_ENVIRONMENT ?? detectEnvironment();

    pyroscope.init({
      appName: DEFAULTS.TELEMETRY.SERVICE_NAME,
      serverAddress: DEFAULTS.TELEMETRY.PROFILING_ENDPOINT,
      basicAuthUser: 'otlp',
      basicAuthPassword: 'J3EPiN69oc1kOF0_KDNT8mUDIoFII9K0e8e1zg4UY3U',
      tags: {
        command: commandName,
        environment: env,
      },
    });

    pyroscope.startCpuProfiling();
    pyroscope.startHeapProfiling();
  } catch {
    // Fail silently — native module may not be available
  }
}

/**
 * Stop profiling and flush data.
 */
export async function stopProfiling(): Promise<void> {
  try {
    const pyroscope = loadPyroscope();
    if (!pyroscope) return;
    await pyroscope.stopCpuProfiling();
    await pyroscope.stopHeapProfiling();
  } catch {
    // Fail silently
  }
}
