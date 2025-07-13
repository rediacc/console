import { invoke } from '@tauri-apps/api/core'

interface AppConfig {
  apiUrl: string
  domain: string
  httpPort: number
  environment: 'development' | 'production'
}

class ConfigService {
  private config: AppConfig | null = null
  private isDesktop = false

  constructor() {
    this.detectEnvironment()
  }

  private async detectEnvironment() {
    try {
      // Check if we're in Tauri/desktop mode
      if (window.__TAURI__) {
        this.isDesktop = true
      }
    } catch {
      this.isDesktop = false
    }
  }

  async getConfig(): Promise<AppConfig> {
    if (this.config) {
      return this.config
    }

    await this.detectEnvironment()

    if (this.isDesktop) {
      // In desktop mode, try to get config from the system
      try {
        // Try to read from system environment or config file
        const systemConfig = await this.getDesktopConfig()
        this.config = systemConfig
      } catch (error) {
        // Failed to load desktop config, using defaults
        this.config = this.getDefaultConfig()
      }
    } else {
      // In web mode, use Vite environment variables
      this.config = {
        apiUrl: import.meta.env.VITE_API_URL || this.getDefaultConfig().apiUrl,
        domain: import.meta.env.VITE_SYSTEM_DOMAIN || 'localhost',
        httpPort: parseInt(import.meta.env.VITE_HTTP_PORT || '7322'),
        environment: import.meta.env.MODE as 'development' | 'production'
      }
    }

    return this.config
  }

  private async getDesktopConfig(): Promise<AppConfig> {
    try {
      // Try to invoke a Tauri command to get system config
      const config = await invoke<AppConfig>('get_system_config')
      return config
    } catch {
      // If that fails, try to read a local config file
      return this.readLocalConfig()
    }
  }

  private async readLocalConfig(): Promise<AppConfig> {
    try {
      // Try to read from user's home directory
      const fs = await import('@tauri-apps/plugin-fs')
      const { homeDir, join } = await import('@tauri-apps/api/path')
      
      const configPath = await join(await homeDir(), '.rediacc', 'console-config.json')
      const configData = await fs.readTextFile(configPath)
      
      return JSON.parse(configData)
    } catch {
      // If all else fails, return defaults
      return this.getDefaultConfig()
    }
  }

  private getDefaultConfig(): AppConfig {
    return {
      apiUrl: 'http://localhost:7322/api',
      domain: 'localhost',
      httpPort: 7322,
      environment: 'production'
    }
  }

  // Get specific config values
  async getApiUrl(): Promise<string> {
    const config = await this.getConfig()
    return config.apiUrl
  }

  async getDomain(): Promise<string> {
    const config = await this.getConfig()
    return config.domain
  }

  async getHttpPort(): Promise<number> {
    const config = await this.getConfig()
    return config.httpPort
  }

  // Update config (for desktop mode)
  async updateConfig(newConfig: Partial<AppConfig>): Promise<void> {
    const currentConfig = await this.getConfig()
    this.config = { ...currentConfig, ...newConfig }
    
    if (this.isDesktop) {
      // Save to local config file
      try {
        const fs = await import('@tauri-apps/plugin-fs')
        const { homeDir, join } = await import('@tauri-apps/api/path')
        
        const configDir = await join(await homeDir(), '.rediacc')
        const configPath = await join(configDir, 'console-config.json')
        
        // Ensure directory exists
        await fs.mkdir(configDir, { recursive: true })
        
        // Write config
        await fs.writeTextFile(configPath, JSON.stringify(this.config, null, 2))
      } catch (error) {
        // Failed to save config
      }
    }
  }
}

export const configService = new ConfigService()