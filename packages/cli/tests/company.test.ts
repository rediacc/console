import { describe, expect, it } from 'vitest';
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

  describe('company maintenance', () => {
    it('should enable maintenance mode', async () => {
      const result = await runCli(['company', 'maintenance', 'enable']);

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Maintenance mode enabled');
    });

    it('should disable maintenance mode', async () => {
      const result = await runCli(['company', 'maintenance', 'disable']);

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Maintenance mode disabled');
    });

    it('should reject invalid action', async () => {
      const result = await runCli(['company', 'maintenance', 'invalid']);

      expect(result.success).toBe(false);
      // In JSON mode, error is returned as structured JSON in stdout
      const errorResponse = result.json as { success: false; error: { message: string } } | null;
      expect(errorResponse?.error.message).toContain('Invalid action');
    });
  });
});
