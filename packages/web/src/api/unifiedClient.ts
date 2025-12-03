import { apiClient as webApiClient } from './client'

class UnifiedApiClient {
  async post<T = unknown>(endpoint: string, data?: unknown) {
    return webApiClient.post<T>(endpoint, data)
  }

  // Desktop-specific methods (always throw in web mode)
  async executePythonScript(_scriptPath: string, _args: string[] = []) {
    throw new Error('Python execution is not available in web mode')
  }

  async syncFiles(
    _direction: 'upload' | 'download',
    _machine: string,
    _repo: string,
    _localPath: string,
    _options: Record<string, unknown> = {}
  ) {
    throw new Error('File sync is not available in web mode')
  }

  async executeTerminalCommand(
    _machine: string,
    _repo: string,
    _command: string,
    _team?: string
  ) {
    throw new Error('Terminal commands are not available in web mode')
  }

  // Environment checks
  async isDesktopMode(): Promise<boolean> {
    return false
  }

  async checkPythonAvailable(): Promise<boolean> {
    return false
  }

  async getPythonVersion(): Promise<string | null> {
    return null
  }

  async checkCliAvailable(): Promise<boolean> {
    return false
  }

  async getSystemInfo(): Promise<Record<string, unknown> | null> {
    return null
  }

  async executePluginCommand(
    _action: 'list' | 'connect' | 'connections',
    _machine: string,
    _repo: string,
    _options: Record<string, unknown> = {}
  ) {
    throw new Error('Plugin commands are not available in web mode')
  }
}

// Export a singleton instance
export const unifiedApiClient = new UnifiedApiClient()

// Command result type for compatibility
export interface CommandResult {
  success: boolean
  output: string
  error: string
}
