
import { RediaccConfig } from '@/types'

interface AppConfig {
  apiUrl: string
  domain: string
  httpPort: number
  environment: 'development' | 'production'
  // Extended configuration from nginx
  instanceName?: string
  enableDebug?: boolean
  enableAnalytics?: boolean
  enableMaintenance?: boolean
  version?: string
  buildTime?: string
  maxUploadSize?: number
  sessionTimeout?: number
  defaultLanguage?: string
  docsUrl?: string
  supportUrl?: string
  csrfEnabled?: boolean
  httpsOnly?: boolean
  customConfig?: any
}

class ConfigService {
  private config: AppConfig | null = null

  private parseRediaccConfig(): Partial<AppConfig> | null {
    if (!window.REDIACC_CONFIG) {
      return null
    }

    const rConfig = window.REDIACC_CONFIG
    
    try {
      return {
        instanceName: rConfig.instanceName || undefined,
        apiUrl: rConfig.apiUrl || undefined,
        domain: rConfig.domain || undefined,
        httpPort: rConfig.httpPort ? parseInt(rConfig.httpPort) : undefined,
        environment: rConfig.environment as 'development' | 'production' || undefined,
        enableDebug: rConfig.enableDebug === 'true',
        enableAnalytics: rConfig.enableAnalytics === 'true',
        enableMaintenance: rConfig.enableMaintenance === 'true',
        version: rConfig.version || undefined,
        buildTime: rConfig.buildTime || undefined,
        maxUploadSize: rConfig.maxUploadSize ? parseInt(rConfig.maxUploadSize) : undefined,
        sessionTimeout: rConfig.sessionTimeout ? parseInt(rConfig.sessionTimeout) : undefined,
        defaultLanguage: rConfig.defaultLanguage || undefined,
        docsUrl: rConfig.docsUrl || undefined,
        supportUrl: rConfig.supportUrl || undefined,
        csrfEnabled: rConfig.csrfEnabled === 'true',
        httpsOnly: rConfig.httpsOnly === 'true',
        customConfig: rConfig.customConfig ? JSON.parse(rConfig.customConfig) : undefined
      }
    } catch (error) {
      console.error('Failed to parse REDIACC_CONFIG:', error)
      return null
    }
  }

  async getConfig(): Promise<AppConfig> {
    if (this.config) {
      return this.config
    }

    // First, try to get config from window.REDIACC_CONFIG (nginx runtime config)
    const runtimeConfig = this.parseRediaccConfig()
    
    // Then fall back to Vite environment variables
    const viteConfig = {
      apiUrl: import.meta.env.VITE_API_URL || this.getDefaultConfig().apiUrl,
      domain: import.meta.env.VITE_SYSTEM_DOMAIN || 'localhost',
      httpPort: parseInt(import.meta.env.VITE_HTTP_PORT || '7322'),
      environment: import.meta.env.MODE as 'development' | 'production'
    }

    // Merge configs: runtime config takes precedence over vite config
    this.config = {
      ...this.getDefaultConfig(),
      ...viteConfig,
      ...runtimeConfig
    } as AppConfig

    // Log configuration source in debug mode
    if (this.config.enableDebug) {
      console.log('Configuration loaded:', {
        source: runtimeConfig ? 'Runtime (nginx)' : 'Build-time (Vite)',
        config: this.config
      })
    }

    return this.config
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

  // Update config
  async updateConfig(newConfig: Partial<AppConfig>): Promise<void> {
    const currentConfig = await this.getConfig()
    this.config = { ...currentConfig, ...newConfig }
  }

  // Extended config getters
  async getInstanceName(): Promise<string> {
    const config = await this.getConfig()
    return config.instanceName || 'default'
  }

  async getVersion(): Promise<string | undefined> {
    const config = await this.getConfig()
    return config.version
  }

  async isDebugEnabled(): Promise<boolean> {
    const config = await this.getConfig()
    return config.enableDebug || false
  }

  async isMaintenanceMode(): Promise<boolean> {
    const config = await this.getConfig()
    return config.enableMaintenance || false
  }

  async getMaxUploadSize(): Promise<number> {
    const config = await this.getConfig()
    return config.maxUploadSize || 10485760 // Default 10MB
  }

  async getSessionTimeout(): Promise<number> {
    const config = await this.getConfig()
    return config.sessionTimeout || 3600 // Default 1 hour
  }

  async getDefaultLanguage(): Promise<string> {
    const config = await this.getConfig()
    return config.defaultLanguage || 'en'
  }

  // Check if configuration is from runtime (nginx) or build-time (vite)
  isRuntimeConfig(): boolean {
    return !!window.REDIACC_CONFIG
  }
}

export const configService = new ConfigService()