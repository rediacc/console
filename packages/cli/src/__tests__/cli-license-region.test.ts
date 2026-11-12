import { afterEach, describe, expect, it, vi } from 'vitest';

const setFreeLicenseRegion = vi.hoisted(() => vi.fn());
vi.mock('../services/account/free-license.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/account/free-license.js')>()),
  setFreeLicenseRegion,
}));

const setAcceptTermsFlag = vi.hoisted(() => vi.fn());
vi.mock('../services/account/terms.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/account/terms.js')>()),
  setAcceptTermsFlag,
}));

import { createCli } from '../cli.js';

// `--region` belongs to machine provisioning, so the free-licence pick is the root `--license-region`.
describe('root --license-region reaches setFreeLicenseRegion', () => {
  afterEach(() => {
    setFreeLicenseRegion.mockClear();
    setAcceptTermsFlag.mockClear();
  });

  async function run(args: string[]): Promise<void> {
    const cli = createCli();
    cli.command('region-probe').action(() => undefined);
    await cli.parseAsync(['node', 'rdc', 'region-probe', ...args]);
  }

  it('passes the id through', async () => {
    await run(['--license-region', 'us']);
    expect(setFreeLicenseRegion).toHaveBeenCalledWith('us');
  });

  it('control: without the option it is not called', async () => {
    await run([]);
    expect(setFreeLicenseRegion).not.toHaveBeenCalled();
  });

  it('an empty value is passed on (and refused downstream), not treated as absent', async () => {
    await run(['--license-region', '']);
    expect(setFreeLicenseRegion).toHaveBeenCalledWith('');
  });

  it('root --accept-terms reaches setAcceptTermsFlag(true); without it nothing is set', async () => {
    await run(['--accept-terms']);
    expect(setAcceptTermsFlag).toHaveBeenCalledWith(true);
    setAcceptTermsFlag.mockClear();
    await run([]);
    expect(setAcceptTermsFlag).not.toHaveBeenCalled();
  });
});
