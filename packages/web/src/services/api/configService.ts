import { CONFIG_URLS } from '@/utils/apiConstants';
import { apiConnectionService } from './apiConnectionService';

interface AppConfig {
  apiUrl: string;
  domain: string;
  httpPort: number;
  environment: 'development' | 'production';
  buildType: 'DEBUG' | 'RELEASE';
  // Extended configuration from web server
  instanceName?: string;
  enableDebug?: boolean;
  enableAnalytics?: boolean;
  enableMaintenance?: boolean;
  version?: string;
  buildTime?: string;
  maxUploadSize?: number;
  sessionTimeout?: number;
  defaultLanguage?: string;
  docsUrl?: string;
  supportUrl?: string;
  csrfEnabled?: boolean;
  httpsOnly?: boolean;
  templatesUrl?: string;
  customConfig?: Record<string, unknown>;
}

class ConfigService {
  private config: AppConfig | null = null;

  private parseRediaccConfig(): Partial<AppConfig> | null {
    if (!window.REDIACC_CONFIG) {
      return null;
    }

    const rConfig = window.REDIACC_CONFIG;

    try {
      return {
        instanceName: rConfig.instanceName || undefined,
        apiUrl: rConfig.apiUrl || undefined,
        domain: rConfig.domain || undefined,
        httpPort: rConfig.httpPort ? Number.parseInt(rConfig.httpPort) : undefined,
        environment: rConfig.environment
          ? (rConfig.environment as 'development' | 'production')
          : undefined,
        enableDebug: rConfig.enableDebug === 'true',
        enableAnalytics: rConfig.enableAnalytics === 'true',
        enableMaintenance: rConfig.enableMaintenance === 'true',
        version: rConfig.version || undefined,
        buildTime: rConfig.buildTime || undefined,
        maxUploadSize: rConfig.maxUploadSize ? Number.parseInt(rConfig.maxUploadSize) : undefined,
        sessionTimeout: rConfig.sessionTimeout
          ? Number.parseInt(rConfig.sessionTimeout)
          : undefined,
        defaultLanguage: rConfig.defaultLanguage || undefined,
        docsUrl: rConfig.docsUrl || undefined,
        supportUrl: rConfig.supportUrl || undefined,
        csrfEnabled: rConfig.csrfEnabled === 'true',
        httpsOnly: rConfig.httpsOnly === 'true',
        templatesUrl: rConfig.templatesUrl || undefined,
        customConfig: rConfig.customConfig
          ? (JSON.parse(rConfig.customConfig) as Record<string, unknown>)
          : undefined,
      };
    } catch (error) {
      console.error('Failed to parse REDIACC_CONFIG:', error);
      return null;
    }
  }

  async getConfig(): Promise<AppConfig> {
    if (this.config) {
      return this.config;
    }

    // First, try to get config from window.REDIACC_CONFIG (web server runtime config)
    const runtimeConfig = this.parseRediaccConfig();

    // Get the selected API endpoint from the connection service
    const selectedEndpoint = await apiConnectionService.performStartupHealthCheck();

    // Then fall back to Vite environment variables
    const viteConfig = {
      apiUrl: selectedEndpoint.url,
      domain: (import.meta.env.VITE_SYSTEM_DOMAIN as string | undefined) ?? 'localhost',
      httpPort: Number.parseInt((import.meta.env.VITE_HTTP_PORT as string | undefined) ?? '7322'),
      environment: import.meta.env.MODE as 'development' | 'production',
      buildType: apiConnectionService.getBuildType(),
    };

    // Merge configs: runtime config takes precedence over vite config
    const mergedConfig: AppConfig = {
      ...this.getDefaultConfig(),
      ...viteConfig,
      ...runtimeConfig,
    };
    this.config = mergedConfig;

    // Log configuration source in debug mode
    if (this.config.enableDebug || this.config.buildType === 'DEBUG') {
      console.warn('Configuration loaded:', {
        source: runtimeConfig ? 'Runtime (web server)' : 'Build-time (Vite)',
        endpoint: selectedEndpoint,
        config: this.config,
      });
    }

    return this.config;
  }

  private getDefaultConfig(): AppConfig {
    return {
      apiUrl: 'http://localhost:7322/api',
      domain: 'localhost',
      httpPort: 7322,
      environment: 'production',
      buildType: 'DEBUG',
    };
  }

  // Get specific config values
  async getApiUrl(): Promise<string> {
    const config = await this.getConfig();
    return config.apiUrl;
  }

  async getDomain(): Promise<string> {
    const config = await this.getConfig();
    return config.domain;
  }

  async getHttpPort(): Promise<number> {
    const config = await this.getConfig();
    return config.httpPort;
  }

  // Update config
  async updateConfig(newConfig: Partial<AppConfig>): Promise<void> {
    const currentConfig = await this.getConfig();
    this.config = { ...currentConfig, ...newConfig };
  }

  // Extended config getters
  async getInstanceName(): Promise<string> {
    const config = await this.getConfig();
    return config.instanceName ?? 'default';
  }

  async getVersion(): Promise<string | undefined> {
    const config = await this.getConfig();
    return config.version;
  }

  async isDebugEnabled(): Promise<boolean> {
    const config = await this.getConfig();
    return config.enableDebug ?? false;
  }

  async isMaintenanceMode(): Promise<boolean> {
    const config = await this.getConfig();
    return config.enableMaintenance ?? false;
  }

  async getMaxUploadSize(): Promise<number> {
    const config = await this.getConfig();
    return config.maxUploadSize ?? 10485760; // Default 10MB
  }

  async getSessionTimeout(): Promise<number> {
    const config = await this.getConfig();
    return config.sessionTimeout ?? 3600; // Default 1 hour
  }

  async getDefaultLanguage(): Promise<string> {
    const config = await this.getConfig();
    return config.defaultLanguage ?? 'en';
  }

  async getTemplatesUrl(): Promise<string> {
    const config = await this.getConfig();
    return config.templatesUrl ?? CONFIG_URLS.TEMPLATES;
  }

  // Check if configuration is from runtime (nginx) or build-time (vite)
  isRuntimeConfig(): boolean {
    return !!window.REDIACC_CONFIG;
  }
}

export const configService = new ConfigService();
