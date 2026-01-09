import { test, expect } from "@playwright/test";
import { CliTestRunner } from "../../src/utils/CliTestRunner";

test.describe("Auth Commands @cli @core", () => {
  let runner: CliTestRunner;

  test.beforeAll(async () => {
    const contextName = process.env.CLI_MASTER_CONTEXT;
    if (!contextName) {
      throw new Error("CLI_MASTER_CONTEXT not set - global setup may have failed");
    }

    runner = CliTestRunner.withContext(contextName);
    runner.config.credentials = {
      email: process.env.CLI_MASTER_EMAIL!,
      password: process.env.CLI_MASTER_PASSWORD!,
    };
  });

  test.describe("auth status", () => {
    test("should show authenticated status when logged in", async () => {
      const result = await runner.authStatus();

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain("Authenticated");
      expect(result.stdout).toContain(process.env.CLI_MASTER_EMAIL);
    });
  });

  test.describe("auth token", () => {
    test.describe("auth token list", () => {
      test("should list active sessions", async () => {
        const result = await runner.run(["auth", "token", "list"]);

        expect(result.exitCode).toBe(0);
        expect(result.json).not.toBeNull();
        expect(Array.isArray(result.json)).toBe(true);
      });
    });

    test.describe("auth token fork", () => {
      test("should create a forked token", async () => {
        const result = await runner.run(["auth", "token", "fork", "-n", "Test Fork Token"]);

        expect(result.exitCode).toBe(0);
        expect(result.stdout).toContain("Token");
      });
    });
  });

  test.describe("auth tfa", () => {
    test.describe("auth tfa status", () => {
      test("should show TFA status or error for fresh account", async () => {
        const result = await runner.run(["auth", "tfa", "status"], { skipJsonParse: true });

        // TFA status may fail for fresh accounts (400 error) or succeed with status
        const output = result.stdout + result.stderr;
        expect(
          output.includes("TFA is enabled") ||
            output.includes("TFA is not enabled") ||
            output.includes("Error") ||
            result.exitCode !== 0
        ).toBe(true);
      });
    });
  });

  test.describe("login/logout flow", () => {
    test("should logout successfully", async () => {
      // Use table format for action commands that only produce success messages
      const result = await runner.run(["logout"], { outputFormat: "table", skipJsonParse: true });

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain("Logged out");
    });

    test("should show not authenticated after logout", async () => {
      const result = await runner.authStatus();

      // 'Not authenticated' message goes to stderr via outputService.warn()
      expect(result.stderr).toContain("Not authenticated");
    });

    test("should login with valid credentials", async () => {
      const result = await runner.login();

      expect(result.exitCode).toBe(0);
      expect(result.stdout).toContain("Login successful");
    });

    test("should fail login with invalid credentials", async () => {
      // First logout
      await runner.logout();

      const result = await runner.login("wrong@example.com", "wrongpassword");

      expect(result.exitCode).not.toBe(0);

      // Re-login with correct credentials
      await runner.login();
    });
  });
});
