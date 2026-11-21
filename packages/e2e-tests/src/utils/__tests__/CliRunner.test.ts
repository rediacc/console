import { afterEach, describe, expect, it } from 'vitest';
import { CliRunner } from '../CliRunner';

const envOf = (runner: CliRunner): NodeJS.ProcessEnv =>
  (runner as unknown as { env: NodeJS.ProcessEnv }).env;

describe('CliRunner environment', () => {
  const saved = process.env.REDIACC_NO_PROVISION;
  afterEach(() => {
    if (saved === undefined) delete process.env.REDIACC_NO_PROVISION;
    else process.env.REDIACC_NO_PROVISION = saved;
  });

  it("carries REDIACC_NO_PROVISION '0' so a development build converges the machine renet", () => {
    process.env.REDIACC_NO_PROVISION = '1';
    expect(envOf(CliRunner.create()).REDIACC_NO_PROVISION).toBe('0');
  });

  it('lets options.env override REDIACC_NO_PROVISION (control)', () => {
    expect(
      envOf(CliRunner.create({ env: { REDIACC_NO_PROVISION: '1' } })).REDIACC_NO_PROVISION
    ).toBe('1');
  });
});
