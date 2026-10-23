import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

/**
 * The installed @pyroscope/nodejs, loaded the way profiling.ts loads it, still offers the five calls that file's
 * PyroscopeModule interface declares, and runs them. A major bump that renames or drops one, throws on the init call
 * profiling.ts makes, or stops resolving a stop call fails here instead of turning profiling into a silent no-op
 * (loadPyroscope swallows every load error). Whether init still honours each option is not checked.
 */
describe('@pyroscope/nodejs contract used by profiling.ts', () => {
  const cjsRequire = createRequire(import.meta.url);
  const mod = cjsRequire('@pyroscope/nodejs');
  const pyroscope = mod.default ?? mod;

  it('exports init and the CPU and heap start/stop calls as functions', () => {
    for (const name of [
      'init',
      'startCpuProfiling',
      'startHeapProfiling',
      'stopCpuProfiling',
      'stopHeapProfiling',
    ]) {
      expect(typeof pyroscope[name], name).toBe('function');
    }
  });

  it('initialises against an unreachable server and starts and stops both profilers', async () => {
    pyroscope.init({
      appName: 'rdc-contract-test',
      serverAddress: 'http://127.0.0.1:9',
      basicAuthUser: '',
      basicAuthPassword: '',
      tags: {},
    });
    pyroscope.startCpuProfiling();
    pyroscope.startHeapProfiling();
    await expect(pyroscope.stopCpuProfiling()).resolves.toBeUndefined();
    await expect(pyroscope.stopHeapProfiling()).resolves.toBeUndefined();
  });
});
