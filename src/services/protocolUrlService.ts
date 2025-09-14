/**
 * Protocol URL Service for Rediacc Custom Protocol Handler
 * Generates and handles rediacc:// URLs for desktop app integration
 */

export type ProtocolAction = 'sync' | 'terminal' | 'plugin' | 'browser'

export interface ProtocolError {
  type: 'timeout' | 'exception' | 'not-installed' | 'permission-denied'
  message: string
}

export interface ProtocolUrlParams {
  token: string
  team: string
  machine: string
  repository: string
  action?: ProtocolAction
  queryParams?: Record<string, string | number | boolean>
}

export interface SyncParams {
  direction?: 'upload' | 'download'
  localPath?: string
  mirror?: boolean
  verify?: boolean
  preview?: boolean
  autoStart?: boolean
}

export interface TerminalParams {
  command?: string
  autoExecute?: boolean
  terminalType?: 'repo' | 'machine'
  fontSize?: number
}

export interface PluginParams {
  name?: string
  port?: string | number
  autoConnect?: boolean
  openBrowser?: boolean
  waitTimeout?: number
}

export interface BrowserParams {
  path?: string
  view?: 'list' | 'grid' | 'tree'
  showHidden?: boolean
  sortBy?: 'name' | 'size' | 'date'
  sortOrder?: 'asc' | 'desc'
}

export interface WindowParams {
  popup?: boolean
  fullscreen?: boolean
  minimize?: boolean
  alwaysOnTop?: boolean
  x?: number
  y?: number
  width?: number
  height?: number
  theme?: 'dark' | 'light'
  lang?: 'en' | 'ar' | 'de'
}

class ProtocolUrlService {
  private readonly PROTOCOL_SCHEME = 'rediacc'

  /**
   * Generate a protocol URL with the given parameters
   */
  generateUrl(params: ProtocolUrlParams): string {
    const { token, team, machine, repository, action, queryParams } = params

    // Build path components
    const pathParts = [
      encodeURIComponent(token),
      encodeURIComponent(team),
      encodeURIComponent(machine),
      encodeURIComponent(repository)
    ]

    // Add action if specified
    if (action) {
      pathParts.push(action)
    }

    // Build base URL
    let url = `${this.PROTOCOL_SCHEME}://${pathParts.join('/')}`

    // Add query parameters if any
    if (queryParams && Object.keys(queryParams).length > 0) {
      const searchParams = new URLSearchParams()
      
      Object.entries(queryParams).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          // Convert boolean to yes/no for consistency with CLI
          if (typeof value === 'boolean') {
            searchParams.append(key, value ? 'yes' : 'no')
          } else {
            searchParams.append(key, String(value))
          }
        }
      })

      const queryString = searchParams.toString()
      if (queryString) {
        url += `?${queryString}`
      }
    }

    return url
  }

  /**
   * Generate a sync-specific URL
   */
  generateSyncUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    syncParams?: SyncParams,
    windowParams?: WindowParams
  ): string {
    return this.generateUrl({
      ...baseParams,
      action: 'sync',
      queryParams: {
        ...syncParams,
        ...windowParams
      }
    })
  }

  /**
   * Generate a terminal-specific URL
   */
  generateTerminalUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    terminalParams?: TerminalParams,
    windowParams?: WindowParams
  ): string {
    return this.generateUrl({
      ...baseParams,
      action: 'terminal',
      queryParams: {
        ...terminalParams,
        ...windowParams
      }
    })
  }

  /**
   * Generate a plugin-specific URL
   */
  generatePluginUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    pluginParams?: PluginParams,
    windowParams?: WindowParams
  ): string {
    return this.generateUrl({
      ...baseParams,
      action: 'plugin',
      queryParams: {
        ...pluginParams,
        ...windowParams
      }
    })
  }

  /**
   * Generate a browser-specific URL
   */
  generateBrowserUrl(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>,
    browserParams?: BrowserParams,
    windowParams?: WindowParams
  ): string {
    return this.generateUrl({
      ...baseParams,
      action: 'browser',
      queryParams: {
        ...browserParams,
        ...windowParams
      }
    })
  }

  /**
   * Open a protocol URL
   * Uses window.open to trigger the protocol handler
   * Returns a promise that attempts to detect if the protocol handler was triggered
   */
  async openUrl(url: string): Promise<{ success: boolean; error?: ProtocolError }> {
    return new Promise((resolve) => {
      let handled = false
      
      // Set up a timeout - if nothing happens in 3 seconds, assume failure
      const timeout = setTimeout(() => {
        if (!handled) {
          handled = true
          resolve({ 
            success: false, 
            error: { 
              type: 'timeout', 
              message: 'Protocol handler did not respond' 
            } 
          })
        }
      }, 3000)
      
      // Listen for blur event - might indicate protocol handler opened
      const handleBlur = () => {
        if (!handled) {
          handled = true
          clearTimeout(timeout)
          window.removeEventListener('blur', handleBlur)
          resolve({ success: true })
        }
      }
      
      window.addEventListener('blur', handleBlur)
      
      try {
        // Use window.open with _self to replace current tab behavior
        // This triggers the protocol handler without opening a new tab
        window.open(url, '_self')
      } catch (error) {
        handled = true
        clearTimeout(timeout)
        window.removeEventListener('blur', handleBlur)
        resolve({ 
          success: false, 
          error: { 
            type: 'exception', 
            message: error instanceof Error ? error.message : 'Unknown error' 
          } 
        })
      }
    })
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
      const testUrl = `${this.PROTOCOL_SCHEME}://test`
      const iframe = document.createElement('iframe')
      iframe.style.display = 'none'
      
      return new Promise<boolean>((resolve) => {
        let timeout: number
        
        // If protocol handler exists, the iframe won't load
        iframe.onerror = () => {
          clearTimeout(timeout)
          document.body.removeChild(iframe)
          resolve(true)
        }
        
        iframe.onload = () => {
          clearTimeout(timeout)
          document.body.removeChild(iframe)
          resolve(false)
        }
        
        // Timeout after 2 seconds - assume not installed
        timeout = setTimeout(() => {
          document.body.removeChild(iframe)
          resolve(false)
        }, 2000)
        
        document.body.appendChild(iframe)
        iframe.src = testUrl
      })
    } catch {
      // If iframe method fails, we can't determine availability
      return false
    }
  }

  /**
   * Check protocol registration status with enhanced detection
   * Returns detailed information about the protocol availability
   */
  async checkProtocolStatus(): Promise<{
    available: boolean;
    method: 'iframe' | 'navigation' | 'unknown';
    confidence: 'high' | 'medium' | 'low';
    errorReason?: string;
  }> {
    // Method 1: Try iframe-based detection
    try {
      const iframeResult = await this.checkProtocolAvailable()
      if (iframeResult) {
        return {
          available: true,
          method: 'iframe',
          confidence: 'medium'
        }
      }
    } catch (error) {
      // Continue to next method
    }

    // Method 2: Try navigation-based detection (more aggressive)
    try {
      const testUrl = `${this.PROTOCOL_SCHEME}://status-check/test/test/test`
      
      return new Promise<{
        available: boolean;
        method: 'iframe' | 'navigation' | 'unknown';
        confidence: 'high' | 'medium' | 'low';
        errorReason?: string;
      }>((resolve) => {
        let resolved = false
        
        // Create a hidden window/tab to test protocol
        const testWindow = window.open('', '_blank', 'width=1,height=1,left=-1000,top=-1000')
        
        if (!testWindow) {
          resolve({
            available: false,
            method: 'unknown',
            confidence: 'low',
            errorReason: 'Popup blocked'
          })
          return
        }

        // Set up timeout
        const timeout: number = setTimeout(() => {
          if (!resolved) {
            resolved = true
            try {
              testWindow.close()
            } catch (e) {
              // Ignore close errors
            }
            resolve({
              available: false,
              method: 'navigation',
              confidence: 'medium',
              errorReason: 'Timeout - protocol handler may not be registered'
            })
          }
        }, 3000)

        // If the protocol handler is registered, the test window should handle the URL
        // and we won't be able to access its location due to cross-origin restrictions
        try {
          testWindow.location.href = testUrl
          
          // Check if window was redirected (indicates protocol handler worked)
          setTimeout(() => {
            if (!resolved) {
              try {
                // If we can still access the window's location, protocol didn't work
                const location = testWindow.location.href
                resolved = true
                clearTimeout(timeout)
                testWindow.close()
                
                if (location === testUrl || location === 'about:blank') {
                  resolve({
                    available: false,
                    method: 'navigation',
                    confidence: 'high',
                    errorReason: 'Protocol handler not registered'
                  })
                } else {
                  resolve({
                    available: true,
                    method: 'navigation',
                    confidence: 'high'
                  })
                }
              } catch (e) {
                // Cross-origin error means protocol handler likely worked
                resolved = true
                clearTimeout(timeout)
                try {
                  testWindow.close()
                } catch (closeError) {
                  // Ignore close errors
                }
                resolve({
                  available: true,
                  method: 'navigation',
                  confidence: 'medium'
                })
              }
            }
          }, 1000)
          
        } catch (error) {
          resolved = true
          clearTimeout(timeout)
          try {
            testWindow.close()
          } catch (e) {
            // Ignore close errors
          }
          resolve({
            available: false,
            method: 'navigation',
            confidence: 'low',
            errorReason: `Navigation error: ${error}`
          })
        }
      })
    } catch (error) {
      return {
        available: false,
        method: 'unknown',
        confidence: 'low',
        errorReason: `Detection failed: ${error}`
      }
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
          'Open PowerShell as Administrator',
          'Navigate to the Rediacc CLI directory',
          'Run: .\\rediacc.ps1 -RegisterProtocol',
          'Restart your browser'
        ]
      },
      {
        platform: 'macOS',
        instructions: [
          'Download and install Rediacc CLI',
          'Open Terminal',
          'Navigate to the Rediacc CLI directory',
          'Run: ./rediacc --register-protocol',
          'You may need to grant permission when prompted'
        ]
      },
      {
        platform: 'Linux',
        instructions: [
          'Download and install Rediacc CLI',
          'Open Terminal',
          'Navigate to the Rediacc CLI directory',
          'Run: ./rediacc --register-protocol',
          'Log out and log back in for changes to take effect'
        ]
      }
    ]
  }

  /**
   * Utility function to create a complete set of URLs for all actions
   */
  generateAllActionUrls(
    baseParams: Omit<ProtocolUrlParams, 'action' | 'queryParams'>
  ): Record<ProtocolAction | 'navigate', string> {
    return {
      navigate: this.generateUrl(baseParams),
      sync: this.generateSyncUrl(baseParams),
      terminal: this.generateTerminalUrl(baseParams),
      plugin: this.generatePluginUrl(baseParams),
      browser: this.generateBrowserUrl(baseParams)
    }
  }
}

// Export singleton instance
export const protocolUrlService = new ProtocolUrlService()