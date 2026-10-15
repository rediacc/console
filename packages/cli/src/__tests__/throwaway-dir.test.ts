import * as os from 'node:os';
import * as path from 'node:path';
import { describe, expect, it } from 'vitest';
import { assertThrowawayDir } from './throwaway-dir.js';

describe('assertThrowawayDir', () => {
  it('admits a directory under the temp directory', () => {
    expect(() =>
      assertThrowawayDir(path.join(os.tmpdir(), 'rdc-cli-test-home-x', 'config'))
    ).not.toThrow();
  });

  it("refuses the developer's real config home, the 2026-10-14 deletion (#61fb7bc3)", () => {
    expect(() => assertThrowawayDir(path.join(os.homedir(), '.config', 'rediacc'))).toThrow(
      /refusing to delete/
    );
  });

  it('refuses the temp directory itself and a sibling that only shares its prefix', () => {
    expect(() => assertThrowawayDir(os.tmpdir())).toThrow(/refusing to delete/);
    expect(() => assertThrowawayDir(`${path.resolve(os.tmpdir())}-other/x`)).toThrow(
      /refusing to delete/
    );
  });
});
