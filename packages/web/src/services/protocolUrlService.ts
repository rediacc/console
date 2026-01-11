/**
 * Protocol URL Service for Rediacc Custom Protocol Handler
 * Generates and handles rediacc:// URLs for desktop app integration
 */

import { apiConnectionService } from '@/services/api';
import { createFreshForkToken } from '@/services/auth';

export type ProtocolAction = 'terminal' | 'file-manager' | 'vscode';

interface ProtocolError {
  type: 'timeout' | 'exception' | 'not-installed' | 'permission-denied';
  message: string;
}

interface ProtocolUrlParams {
  team: string;
  machine: string;
  repository: string;
  action?: ProtocolAction;
  queryParams?: Record<string, string | number | boolean>;
}

interface TerminalParams {
  command?: string;
  autoExecute?: boolean;
  terminalType?: 'repository' | 'machine';
  fontSize?: number;
}

export interface ContainerParams {
  containerId?: string;
  containerName?: string;
  action?: 'terminal' | 'logs' | 'stats' | 'exec';
  command?: string;
  lines?: number;
  follow?: boolean;
  shell?: 'bash' | 'sh' | 'zsh';
}

interface WindowParams {
  popup?: boolean;
  fullscreen?: boolean;
  minimize?: boolean;
  alwaysOnTop?: boolean;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  theme?: 'dark' | 'light';
  lang?: 'en' | 'ar' | 'de';
}

interface VSCodeParams {
  path?: string; // Optional: specific directory to open in VSCode
  windowParams?: WindowParams; // Optional: window customization
}

interface ProtocolWindow extends Window {
  signalProtocolLaunch?: () => void;
}

interface ProtocolStatusResult {
  available: boolean;
  method: 'iframe' | 'navigation' | 'unknown';
  confidence: 'high' | 'medium' | 'low';
  errorReason?: string;
}

/**
 * Utility: Detect protocol handler using navigation-based approach
 */
function detectProtocolHandler(testUrl: string, timeout: number): Promise<ProtocolStatusResult> {
  return new Promise((resolve) => {
    const testWindow = window.open('', '_blank', 'width=1,height=1,left=-1000,top=-1000');

    if (!testWindow) {
      resolve({
        available: false,
        method: 'unknown',
        confidence: 'low',
        errorReason: 'Popup blocked',
      });
      return;
    }

    const cleanup = () => {
      try {
        testWindow.close();
      } catch {
        // Ignore close errors
      }
    };

    try {
      testWindow.location.href = testUrl;
      waitForProtocolConfirmation(testWindow, timeout, cleanup)
        .then(resolve)
        .catch(() => {
          cleanup();
          resolve({
            available: false,
            method: 'navigation',
            confidence: 'medium',
            errorReason: 'Timeout - protocol handler may not be registered',
          });
        });
    } catch (error) {
      cleanup();
      resolve({
        available: false,
        method: 'navigation',
        confidence: 'low',
        errorReason: `Navigation error: ${error}`,
      });
    }
  });
}

/**
 * Utility: Wait for protocol confirmation by checking window state
 */
function waitForProtocolConfirmation(
  testWindow: Window,
  timeout: number,
  cleanup: () => void
): Promise<ProtocolStatusResult> {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => reject(new Error('Timeout')), timeout);

    setTimeout(() => {
      clearTimeout(timeoutId);
      try {
        const location = testWindow.location.href;
        cleanup();

        if (location === testWindow.location.href || location === 'about:blank') {
          resolve({
            available: false,
            method: 'navigation',
            confidence: 'high',
            errorReason: 'Protocol handler not registered',
          });
        } else {
          resolve({
            available: true,
            method: 'navigation',
            confidence: 'high',
          });
        }
      } catch {
        cleanup();
        resolve({
          available: true,
          method: 'navigation',
          confidence: 'medium',
        });
      }
    }, 1000);
  });
}

/**
 * Utility: Build protocol query parameters
 */
function buildProtocolParameters(
  apiUrl: string,
  queryParams?: Record<string, string | number | boolean>
): URLSearchParams {
  const searchParams = new URLSearchParams();
  searchParams.append('apiUrl', apiUrl);

  if (!queryParams) {
    return searchParams;
  }

  for (const [key, value] of Object.entries(queryParams)) {
    if (typeof value === 'boolean') {
      searchParams.append(key, value ? 'yes' : 'no');
    } else {
      searchParams.append(key, String(value));
    }
  }

  return searchParams;
}

/**
 * Utility: Setup protocol listeners for URL opening
 */
function setupProtocolListeners(
  onSuccess: () => void,
  onTimeout: () => void,
  timeoutMs: number
): { cleanup: () => void } {
  let handled = false;

  const timeout = setTimeout(() => {
    if (handled) return;
    handled = true;
    cleanup();
    onTimeout();
  }, timeoutMs);

  const handleBlur = () => {
    if (handled) return;
    handled = true;
    cleanup();
    onSuccess();
  };

  window.addEventListener('blur', handleBlur);

  const cleanup = () => {
    clearTimeout(timeout);
    window.removeEventListener('blur', handleBlur);
  };

  return { cleanup };
}

class ProtocolUrlService {
  private readonly PROTOCOL_SCHEME = 'rediacc';

  /**
   * Generate a protocol URL with the given parameters
   * Fork token will be created automatically for the specified action
   */
  async generateUrl(params: ProtocolUrlParams): Promise<string> {
    const { team, machine, repository, action, queryParams } = params;

    // Get current API URL to include in protocol URL
    let apiUrl = await apiConnectionService.getApiUrl();

    // Convert relative API URL to absolute URL for CLI usage
    if (apiUrl.startsWith('/')) {
      const protocol = window.location.protocol;
      const host = window.location.host;
      apiUrl = `${protocol}//${host}${apiUrl}`;
    }

    // Create fresh fork token for this action (ensures new token per click)
    const actionKey = action ?? 'default';
    const forkToken = await createFreshForkToken(actionKey);

    // Build path components
    const pathParts = [
      encodeURIComponent(forkToken),
      encodeURIComponent(team),
      encodeURIComponent(machine),
    ];

    // Only add repository if it's provided and not empty
    if (repository && repository.trim() !== '') {
      pathParts.push(encodeURIComponent(repository));
    }

    // Add action if specified
    if (action) {
      pathParts.push(action);
    }

    // Build base URL
    let url = `${this.PROTOCOL_SCHEME}://${pathParts.join('/')}`;

    // Build query parameters using utility
    const searchParams = buildProtocolParameters(apiUrl, queryParams);
    const queryString = searchParams.toString();

    if (queryString) {
      url += `?${queryString}`;
    }

    return url;
  }

  /**
   * Generate a terminal-specific URL
   */
  async generateTerminalUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    terminalParams?: TerminalParams,
    windowParams?: WindowParams
  ): Promise<string> {
    return await this.generateUrl({
      ...baseParams,
      action: 'terminal',
      queryParams: {
        ...terminalParams,
        ...windowParams,
      },
    });
  }

  /**
   * Generate a desktop-specific URL
   */
  async generateDesktopUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    containerParams?: ContainerParams,
    windowParams?: WindowParams
  ): Promise<string> {
    return await this.generateUrl({
      ...baseParams,
      action: 'file-manager',
      queryParams: {
        ...containerParams,
        ...windowParams,
      },
    });
  }

  /**
   * Generate a container terminal URL
   */
  async generateContainerTerminalUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    containerParams: ContainerParams,
    windowParams?: WindowParams
  ): Promise<string> {
    return await this.generateUrl({
      ...baseParams,
      action: 'terminal',
      queryParams: {
        terminalType: 'container',
        ...containerParams,
        ...windowParams,
      },
    });
  }

  /**
   * Generate a container logs URL
   */
  async generateContainerLogsUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    containerParams: ContainerParams,
    windowParams?: WindowParams
  ): Promise<string> {
    return await this.generateUrl({
      ...baseParams,
      action: 'terminal',
      queryParams: {
        terminalType: 'container',
        action: 'logs',
        lines: containerParams.lines ?? 100,
        follow: true,
        ...containerParams,
        ...windowParams,
      },
    });
  }

  /**
   * Generate a container stats URL
   */
  async generateContainerStatsUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    containerParams: ContainerParams,
    windowParams?: WindowParams
  ): Promise<string> {
    return await this.generateUrl({
      ...baseParams,
      action: 'terminal',
      queryParams: {
        terminalType: 'container',
        action: 'stats',
        ...containerParams,
        ...windowParams,
      },
    });
  }

  /**
   * Generate a VSCode-specific URL
   * This will launch VSCode with SSH remote connection to the repository or machine
   */
  async generateVSCodeUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    vscodeParams?: VSCodeParams
  ): Promise<string> {
    return await this.generateUrl({
      ...baseParams,
      action: 'vscode',
      queryParams: {
        ...(vscodeParams?.path ? { path: vscodeParams.path } : {}),
        ...(vscodeParams?.windowParams ?? {}),
      },
    });
  }

  /**
   * Open a protocol URL
   * Uses window.open to trigger the protocol handler
   * Returns a promise that attempts to detect if the protocol handler was triggered
   */
  async openUrl(url: string): Promise<{ success: boolean; error?: ProtocolError }> {
    return new Promise((resolve) => {
      const onSuccess = () => resolve({ success: true });
      const onTimeout = () =>
        resolve({
          success: false,
          error: {
            type: 'timeout',
            message: 'Protocol handler did not respond',
          },
        });

      const { cleanup } = setupProtocolListeners(onSuccess, onTimeout, 3000);

      try {
        // Signal that we're about to launch a protocol URL to prevent token wipe
        const protocolWindow = window as ProtocolWindow;
        if (typeof protocolWindow.signalProtocolLaunch === 'function') {
          protocolWindow.signalProtocolLaunch();
        }

        // Use window.open with _self to replace current tab behavior
        window.open(url, '_self');
      } catch (error) {
        cleanup();
        resolve({
          success: false,
          error: {
            type: 'exception',
            message: error instanceof Error ? error.message : 'Unknown error',
          },
        });
      }
    });
  }

  /**
   * Check if the protocol handler is available
   * This is a heuristic check - we can't definitively know if it's installed
   */
  async checkProtocolAvailable(): Promise<boolean> {
    // Try to detect if the protocol handler is registered
    // This is tricky because browsers don't expose this information directly

    // Method 1: Try to open a test URL in an iframe (won't work in all browsers)
    try {
      const testUrl = `${this.PROTOCOL_SCHEME}://test`;
      const iframe = document.createElement('iframe');
      iframe.style.display = 'none';

      return new Promise<boolean>((resolve) => {
        // Timeout after 2 seconds - assume not installed
        setTimeout(() => {
          document.body.removeChild(iframe);
          resolve(false);
        }, 2000);

        document.body.appendChild(iframe);
        iframe.src = testUrl;
      });
    } catch {
      // If iframe method fails, we can't determine availability
      return false;
    }
  }

  /**
   * Check protocol registration status with enhanced detection
   * Returns detailed information about the protocol availability
   */
  async checkProtocolStatus(): Promise<ProtocolStatusResult> {
    // Method 1: Try iframe-based detection
    try {
      const iframeResult = await this.checkProtocolAvailable();
      if (iframeResult) {
        return {
          available: true,
          method: 'iframe',
          confidence: 'medium',
        };
      }
    } catch {
      // Continue to next method
    }

    // Method 2: Try navigation-based detection (more aggressive)
    try {
      const testUrl = `${this.PROTOCOL_SCHEME}://status-check/test/test/test`;
      return await detectProtocolHandler(testUrl, 3000);
    } catch (error) {
      return {
        available: false,
        method: 'unknown',
        confidence: 'low',
        errorReason: `Detection failed: ${error}`,
      };
    }
  }

  /**
   * Get installation instructions for the protocol handler
   */
  getInstallInstructions(): { platform: string; instructions: string[] }[] {
    return [
      {
        platform: 'Windows',
        instructions: [
          'Download and install Rediacc CLI',
          'Open PowerShell or Command Prompt',
          'Run: rediacc protocol register',
          'For system-wide: rediacc protocol register --system-wide (requires Admin)',
          'Restart your browser',
        ],
      },
      {
        platform: 'macOS',
        instructions: [
          'Download and install Rediacc CLI',
          'Open Terminal',
          'Run: ./rediacc protocol register',
          'For system-wide: sudo ./rediacc protocol register --system-wide',
          'You may need to grant permission when prompted',
        ],
      },
      {
        platform: 'Linux',
        instructions: [
          'Download and install Rediacc CLI',
          'Open Terminal',
          'Run: ./rediacc protocol register',
          'For system-wide: sudo ./rediacc protocol register --system-wide',
          'Log out and log back in for changes to take effect',
        ],
      },
    ];
  }

  /**
   * Generate a sync-specific URL
   */
  async generateSyncUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    syncParams?: { direction?: 'upload' | 'download'; path?: string },
    windowParams?: WindowParams
  ): Promise<string> {
    return await this.generateUrl({
      ...baseParams,
      action: 'file-manager',
      queryParams: {
        action: 'sync',
        ...syncParams,
        ...windowParams,
      },
    });
  }

  /**
   * Generate a plugin-specific URL
   */
  async generatePluginUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    pluginParams?: { pluginName?: string; pluginAction?: string },
    windowParams?: WindowParams
  ): Promise<string> {
    return await this.generateUrl({
      ...baseParams,
      action: 'file-manager',
      queryParams: {
        action: 'plugin',
        ...pluginParams,
        ...windowParams,
      },
    });
  }

  /**
   * Generate a browser-specific URL
   */
  async generateBrowserUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    browserParams?: { path?: string; readonly?: boolean },
    windowParams?: WindowParams
  ): Promise<string> {
    return await this.generateUrl({
      ...baseParams,
      action: 'file-manager',
      queryParams: {
        action: 'browser',
        ...browserParams,
        ...windowParams,
      },
    });
  }

  /**
   * Utility function to create a complete set of URLs for all actions
   */
  async generateAllActionUrls(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>
  ): Promise<Record<ProtocolAction | 'navigate', string>> {
    return {
      navigate: await this.generateUrl(baseParams),
      terminal: await this.generateTerminalUrl(baseParams),
      'file-manager': await this.generateDesktopUrl(baseParams),
      vscode: await this.generateVSCodeUrl(baseParams),
    };
  }
}

// Export singleton instance
export const protocolUrlService = new ProtocolUrlService();
