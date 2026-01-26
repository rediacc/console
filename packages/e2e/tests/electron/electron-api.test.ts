import { electronTest, expect, isElectronProject } from '@/electron/ElectronFixture';
// Import types to augment Window with electronAPI
import '@/electron/types';

/**
 * Electron-specific tests for IPC and native functionality.
 *
 * These tests verify that the Electron desktop app's native APIs work correctly.
 * They ONLY run on electron-* projects and are skipped on web browser projects.
 *
 * Tested APIs:
 * - safeStorage: Encrypted storage using OS keyring
 * - app: Application info (name, version)
 * - terminal: SSH terminal API availability
 * - sftp: SFTP file browser API availability
 * - vscode: VS Code Remote SSH launcher API availability
 */
electronTest.describe('Electron IPC Tests @electron', () => {
  electronTest.beforeEach(({ page: _page }, testInfo) => {
    // Skip these tests when not running in an Electron project
    if (!isElectronProject(testInfo.project.name)) {
      electronTest.skip();
    }
  });

  electronTest('should expose electronAPI on window', async ({ page }) => {
    const hasElectronAPI = await page.evaluate(() => {
      return typeof window.electronAPI !== 'undefined';
    });

    expect(hasElectronAPI).toBe(true);
  });

  electronTest('should have safeStorage API available', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const api = window.electronAPI?.safeStorage;
      if (!api || typeof api.isAvailable !== 'function') {
        return { hasApi: false, isAvailable: false };
      }
      // safeStorage.isAvailable() may return false in headless/WSL environments
      // without a proper OS keyring (libsecret on Linux)
      const available = await api.isAvailable();
      return { hasApi: true, isAvailable: available };
    });

    // The API should always be exposed
    expect(result.hasApi).toBe(true);
    // Note: isAvailable may be false in CI/headless environments - that's OK
    if (!result.isAvailable) {
      console.warn('safeStorage is not available (no OS keyring) - skipping availability check');
    }
  });

  electronTest('should encrypt and decrypt data via safeStorage', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const api = window.electronAPI?.safeStorage;
      if (!api) {
        return { success: false, skipped: false, error: 'safeStorage API not available' };
      }

      // Check if safeStorage is available (OS keyring present)
      const isAvailable = await api.isAvailable();
      if (!isAvailable) {
        // Skip test gracefully in environments without OS keyring
        return { success: true, skipped: true, error: 'safeStorage not available (no OS keyring)' };
      }

      try {
        const testData = `e2e-test-secret-data-${Date.now()}`;
        const encrypted = await api.encrypt(testData);

        // Encrypted data should be different from original
        if (encrypted === testData) {
          return { success: false, skipped: false, error: 'Encrypted data is same as original' };
        }

        const decrypted = await api.decrypt(encrypted);

        return {
          success: decrypted === testData,
          skipped: false,
          original: testData,
          decrypted,
        };
      } catch (error) {
        return { success: false, skipped: false, error: String(error) };
      }
    });

    if (result.skipped) {
      console.warn('safeStorage encrypt/decrypt skipped:', result.error);
    } else {
      expect(result.success).toBe(true);
      if (!result.success) {
        console.error('safeStorage test failed:', result.error);
      }
    }
  });

  electronTest('should get app info via main process', async ({ electronApp }) => {
    const appInfo = await electronApp.evaluate(({ app }) => ({
      name: app.getName(),
      version: app.getVersion(),
      locale: app.getLocale(),
      isPackaged: app.isPackaged,
    }));

    // In development mode, app.getName() returns "Electron"
    // In production/packaged mode, it returns "Rediacc Desktop"
    expect(['Electron', 'Rediacc Desktop']).toContain(appInfo.name);
    expect(appInfo.version).toMatch(/^\d+\.\d+\.\d+/);
    // In development/test mode, isPackaged should be false
    expect(appInfo.isPackaged).toBe(false);
  });

  electronTest('should have terminal API available', async ({ page }) => {
    const hasTerminalAPI = await page.evaluate(() => {
      const api = window.electronAPI?.terminal;
      return (
        typeof api !== 'undefined' &&
        typeof api.connect === 'function' &&
        typeof api.write === 'function' &&
        typeof api.resize === 'function' &&
        typeof api.close === 'function'
      );
    });

    expect(hasTerminalAPI).toBe(true);
  });

  electronTest('should have SFTP API available', async ({ page }) => {
    const hasSftpAPI = await page.evaluate(() => {
      const api = window.electronAPI?.sftp;
      return (
        typeof api !== 'undefined' &&
        typeof api.connect === 'function' &&
        typeof api.listDirectory === 'function' &&
        typeof api.readFile === 'function' &&
        typeof api.close === 'function'
      );
    });

    expect(hasSftpAPI).toBe(true);
  });

  electronTest('should have VS Code launch API available', async ({ page }) => {
    const hasVscodeAPI = await page.evaluate(() => {
      const api = window.electronAPI?.vscode;
      return (
        typeof api !== 'undefined' &&
        typeof api.launch === 'function' &&
        typeof api.isAvailable === 'function' &&
        typeof api.hasRemoteSSH === 'function'
      );
    });

    expect(hasVscodeAPI).toBe(true);
  });

  electronTest('should have container API available', async ({ page }) => {
    const hasContainerAPI = await page.evaluate(() => {
      const api = window.electronAPI?.container;
      return (
        typeof api !== 'undefined' &&
        typeof api.exec === 'function' &&
        typeof api.logs === 'function' &&
        typeof api.stats === 'function'
      );
    });

    expect(hasContainerAPI).toBe(true);
  });

  electronTest('should have rsync API available', async ({ page }) => {
    const hasRsyncAPI = await page.evaluate(() => {
      const api = window.electronAPI?.rsync;
      return (
        typeof api !== 'undefined' &&
        typeof api.execute === 'function' &&
        typeof api.preview === 'function' &&
        typeof api.abort === 'function'
      );
    });

    expect(hasRsyncAPI).toBe(true);
  });

  electronTest('should have window popout API available', async ({ page }) => {
    const hasWindowAPI = await page.evaluate(() => {
      const api = window.electronAPI?.window;
      return (
        typeof api !== 'undefined' &&
        typeof api.openPopout === 'function' &&
        typeof api.closePopout === 'function' &&
        typeof api.getPopoutCount === 'function'
      );
    });

    expect(hasWindowAPI).toBe(true);
  });

  electronTest('should have app version API available', async ({ page }) => {
    const appInfo = await page.evaluate(async () => {
      const api = window.electronAPI?.app;
      if (!api) {
        return { success: false, error: 'app API not available' };
      }

      try {
        const version = await api.getVersion();
        const platform = await api.getPlatform();
        const arch = await api.getArch();

        return {
          success: true,
          version,
          platform,
          arch,
        };
      } catch (error) {
        return { success: false, error: String(error) };
      }
    });

    expect(appInfo.success).toBe(true);
    if (appInfo.success) {
      expect(appInfo.version).toMatch(/^\d+\.\d+\.\d+/);
      expect(['darwin', 'linux', 'win32']).toContain(appInfo.platform);
      expect(['x64', 'arm64', 'ia32']).toContain(appInfo.arch);
    }
  });
});
