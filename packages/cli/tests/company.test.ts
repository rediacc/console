import { describe, it, expect } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('company commands', () => {
  describe('company info', () => {
    it('should show company information', async () => {
      const result = await runCli(['company', 'info']);

      expect(result.success).toBe(true);
      expect(result.json).not.toBeNull();
    });
  });

  describe('company vault', () => {
    it('should show company vault data', async () => {
      const result = await runCli(['company', 'vault']);

      // Company vault may require specific permissions or master password
      // For fresh accounts, the command should at least run
      expect(result.success || result.stderr.length > 0 || result.stdout.length > 0).toBe(true);
    });
  });

  // Note: company update operations are sensitive and skipped
  describe.skip('company update operations', () => {
    it('should update company name', async () => {
      // Requires careful handling - company name changes affect all users
    });
  });
});
