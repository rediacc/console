import { expect, test } from '@playwright/test';
import { getPlatform, isWSLAvailable } from '@rediacc/shared-desktop/utils/platform';
import { findVSCode, findAllVSCodeInstallations } from '@rediacc/shared-desktop/vscode';

/**
 * VS Code Detection Tests
 *
 * These tests verify VS Code detection functionality across platforms.
 * They can run standalone without requiring the Elite infrastructure.
 *
 * Tags:
 * - @vscode: VS Code specific tests
 * - @standalone: Tests that don't require API connection
 * - @detection: Tests for executable detection
 */
test.describe('VS Code Detection @vscode @standalone @detection', () => {
  test.describe('Platform Detection', () => {
    test('should detect current platform correctly', () => {
      const platform = getPlatform();

      // Platform should be one of the supported values
      expect(['windows', 'macos', 'linux']).toContain(platform);

      // Platform should match Node.js process.platform
      let expected: string;
      if (process.platform === 'win32') {
        expected = 'windows';
      } else if (process.platform === 'darwin') {
        expected = 'macos';
      } else {
        expected = 'linux';
      }
      expect(platform).toBe(expected);
    });

    test('should check WSL availability on Windows', async () => {
      const platform = getPlatform();

      if (platform === 'windows') {
        // On Windows, isWSLAvailable should return boolean
        const wslAvailable = await isWSLAvailable();
        expect(typeof wslAvailable).toBe('boolean');
      } else {
        // On non-Windows platforms, isWSLAvailable should return false
        const wslAvailable = await isWSLAvailable();
        expect(wslAvailable).toBe(false);
      }
    });
  });

  test.describe('VS Code Detection', () => {
    test('should attempt to find VS Code on current platform', async () => {
      const info = await findVSCode();

      // VS Code may or may not be installed - both are valid outcomes
      if (info) {
        // If found, should have required properties
        expect(info.path).toBeTruthy();
        expect(typeof info.path).toBe('string');
        expect(typeof info.isInsiders).toBe('boolean');

        // Optional properties
        if (info.version) {
          expect(typeof info.version).toBe('string');
        }
        if (info.isWSL !== undefined) {
          expect(typeof info.isWSL).toBe('boolean');
        }
        if (info.wslDistro) {
          expect(typeof info.wslDistro).toBe('string');
        }
      } else {
        // If not found, that's also valid - VS Code isn't required
        expect(info).toBeNull();
      }
    });

    test('should fallback to regular detection when REDIACC_VSCODE_PATH is invalid', async () => {
      // Save original value
      const originalPath = process.env.REDIACC_VSCODE_PATH;

      try {
        // First get the result without env var override
        delete process.env.REDIACC_VSCODE_PATH;
        const normalResult = await findVSCode();

        // Now set to invalid path
        process.env.REDIACC_VSCODE_PATH = '/nonexistent/path/to/code';

        const info = await findVSCode();

        // When env var is invalid, it should fall back to regular detection
        // So result should match normal detection (both null or same VS Code found)
        if (normalResult === null) {
          expect(info).toBeNull();
        } else {
          // If VS Code is installed, fallback should find it
          expect(info).not.toBeNull();
          expect(info?.path).toBe(normalResult.path);
        }
      } finally {
        // Restore original value
        if (originalPath) {
          process.env.REDIACC_VSCODE_PATH = originalPath;
        } else {
          delete process.env.REDIACC_VSCODE_PATH;
        }
      }
    });

    test('should use REDIACC_VSCODE_PATH environment variable when valid', async () => {
      // This test validates that a valid env var path is used
      // We first find VS Code normally, then verify the env var would work

      // Save original value
      const originalPath = process.env.REDIACC_VSCODE_PATH;

      try {
        // Clear the env var to use default detection
        delete process.env.REDIACC_VSCODE_PATH;

        // First call without env var override
        const normalInfo = await findVSCode();

        if (normalInfo) {
          // Set env var to the found VS Code path
          process.env.REDIACC_VSCODE_PATH = normalInfo.path;

          const infoWithOverride = await findVSCode();

          // Should use the env var path
          expect(infoWithOverride).not.toBeNull();
          expect(infoWithOverride?.path).toBe(normalInfo.path);
        } else {
          // VS Code not installed - just verify env var is checked
          // Set to invalid path and verify it still returns null
          process.env.REDIACC_VSCODE_PATH = '/test/invalid/code';
          const info = await findVSCode();
          expect(info).toBeNull();
        }
      } finally {
        // Restore original value
        if (originalPath) {
          process.env.REDIACC_VSCODE_PATH = originalPath;
        } else {
          delete process.env.REDIACC_VSCODE_PATH;
        }
      }
    });
  });

  test.describe('Multi-Installation Detection (Windows Only)', () => {
    test('should detect all VS Code installations on Windows', async () => {
      const platform = getPlatform();

      if (platform !== 'windows') {
        test.skip();
        return;
      }

      const installations = await findAllVSCodeInstallations();

      // Should always return an object with windows and wsl properties
      expect(installations).toBeDefined();
      expect(installations).toHaveProperty('windows');
      expect(installations).toHaveProperty('wsl');

      // Each property should be either VSCodeInfo or null
      if (installations.windows) {
        expect(installations.windows.path).toBeTruthy();
        expect(typeof installations.windows.isInsiders).toBe('boolean');
      }

      if (installations.wsl) {
        expect(installations.wsl.path).toBeTruthy();
        expect(typeof installations.wsl.isInsiders).toBe('boolean');
        expect(installations.wsl.isWSL).toBe(true);
        expect(installations.wsl.wslDistro).toBeTruthy();
      }
    });

    test('should handle WSL not being available gracefully', async () => {
      const platform = getPlatform();

      // This test is meaningful only on Windows without WSL
      if (platform !== 'windows') {
        test.skip();
        return;
      }

      const installations = await findAllVSCodeInstallations();

      // Even if WSL isn't available, should return valid structure
      expect(installations).toBeDefined();
      expect(installations).toHaveProperty('windows');
      expect(installations).toHaveProperty('wsl');

      // If WSL isn't available, wsl should be null
      const wslAvailable = await isWSLAvailable();
      if (!wslAvailable) {
        expect(installations.wsl).toBeNull();
      }
    });
  });

  test.describe('Detection Consistency', () => {
    test('should return consistent results on multiple calls', async () => {
      // Detection should be deterministic
      const info1 = await findVSCode();
      const info2 = await findVSCode();

      // Results should match (both null or both have same path)
      if (info1 === null) {
        expect(info2).toBeNull();
      } else {
        expect(info2).not.toBeNull();
        expect(info2!.path).toBe(info1.path);
        expect(info2!.isInsiders).toBe(info1.isInsiders);
      }
    });
  });
});
