import { afterEach, describe, expect, it } from 'vitest';
import {
  installCloudflareWorkersShim,
  uninstallCloudflareWorkersShim,
} from '../node-workers-shim.js';

const resolveWorkers = () => import.meta.resolve('cloudflare:workers');

describe('cloudflare:workers shim', () => {
  afterEach(() => uninstallCloudflareWorkersShim());

  it('resolves cloudflare:workers while installed and not after uninstall', () => {
    installCloudflareWorkersShim();
    installCloudflareWorkersShim();
    expect(resolveWorkers()).toMatch(/^data:text\/javascript,/);
    uninstallCloudflareWorkersShim();
    expect(resolveWorkers()).not.toMatch(/^data:/);
  });

  it('installs again after an uninstall', () => {
    installCloudflareWorkersShim();
    uninstallCloudflareWorkersShim();
    installCloudflareWorkersShim();
    expect(resolveWorkers()).toMatch(/^data:text\/javascript,/);
  });
});
