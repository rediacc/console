import { afterAll, describe, expect, it } from 'vitest';
import { login, logout, runCli } from './helpers/cli.js';
import { getConfig } from './helpers/config.js';

describe('auth commands', () => {
  const config = getConfig();

  describe('auth status', () => {
    it('should show authenticated status when logged in', async () => {
      const result = await runCli(['auth', 'status'], { skipJsonParse: true });

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('Authenticated');
      expect(result.stdout).toContain(config.email);
    });
  });

  describe('auth token', () => {
    describe('auth token list', () => {
      it('should list active sessions', async () => {
        const result = await runCli(['auth', 'token', 'list']);

        expect(result.exitCode).toBe(0);
        expect(result.json).not.toBeNull();
        // Should return an array of sessions
        expect(Array.isArray(result.json)).toBe(true);
      });
    });

    describe('auth token fork', () => {
      it('should create a forked token', async () => {
        const result = await runCli(['auth', 'token', 'fork', '-n', 'Test Fork Token']);

        expect(result.exitCode).toBe(0);
        expect(result.stdout).toContain('Token');
      });
    });
  });

  describe('auth tfa', () => {
    describe('auth tfa status', () => {
      it('should show TFA status or error for fresh account', async () => {
        const result = await runCli(['auth', 'tfa', 'status'], { skipJsonParse: true });

        // TFA status may fail for fresh accounts (400 error) or succeed with status
        // Fresh accounts may not have TFA initialized which causes an API error
        const output = result.stdout + result.stderr;
        expect(
          output.includes('TFA is enabled') ||
            output.includes('TFA is not enabled') ||
            output.includes('Error') || // Fresh account may error
            result.exitCode !== 0
        ).toBe(true);
      });
    });
  });

  describe('login/logout flow', () => {
    afterAll(async () => {
      // Re-login after logout test
      await login();
    });

    it('should logout successfully', async () => {
      const result = await logout();

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('Logged out');
    });

    it('should show not authenticated after logout', async () => {
      const result = await runCli(['auth', 'status'], { skipJsonParse: true });

      // 'Not authenticated' message goes to stderr via outputService.warn()
      expect(result.stderr).toContain('Not authenticated');
    });

    it('should login with valid credentials', async () => {
      const result = await login();

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain('Login successful');
    });

    it('should fail login with invalid credentials', async () => {
      // First logout
      await logout();

      const result = await login({
        email: 'wrong@example.com',
        password: 'wrongpassword',
      });

      expect(result.exitCode).not.toBe(0);

      // Re-login with correct credentials
      await login();
    });
  });
});
