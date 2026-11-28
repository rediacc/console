import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { getEffectiveConfigName, rdcCommand, setConfigNameOverride } from '../config-name.js';

describe('rdcCommand', () => {
  const savedEnv = process.env.REDIACC_CONFIG;

  beforeEach(() => {
    setConfigNameOverride(null);
    delete process.env.REDIACC_CONFIG;
  });

  afterEach(() => {
    setConfigNameOverride(null);
    if (savedEnv === undefined) delete process.env.REDIACC_CONFIG;
    else process.env.REDIACC_CONFIG = savedEnv;
  });

  it('names the bare command for the default config', () => {
    expect(getEffectiveConfigName()).toBe('rediacc');
    expect(rdcCommand('config remote enable')).toBe('rdc config remote enable');
  });

  it('targets the --config override when one is active', () => {
    setConfigNameOverride('eu-remote');
    expect(rdcCommand('subscription status')).toBe('rdc --config eu-remote subscription status');
  });

  it('targets the REDIACC_CONFIG config when no flag is given', () => {
    process.env.REDIACC_CONFIG = 'eu-bench';
    expect(rdcCommand('config remote enable')).toBe('rdc --config eu-bench config remote enable');
  });

  it('prefers the --config flag over REDIACC_CONFIG', () => {
    process.env.REDIACC_CONFIG = 'from-env';
    setConfigNameOverride('from-flag');
    expect(rdcCommand('x')).toBe('rdc --config from-flag x');
  });

  it('an explicit config name wins over the active one, and the default name stays bare', () => {
    setConfigNameOverride('eu-remote');
    expect(rdcCommand('config remote enable', 'other')).toBe(
      'rdc --config other config remote enable'
    );
    expect(rdcCommand('config remote enable', 'rediacc')).toBe('rdc config remote enable');
  });

  it('shell-quotes a name with characters the shell would split or expand', () => {
    expect(rdcCommand('x', 'my config')).toBe("rdc --config 'my config' x");
    expect(rdcCommand('x', "it's")).toBe("rdc --config 'it'\\''s' x");
  });
});
