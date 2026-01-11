// Runtime configuration from nginx
interface RediaccConfig {
  // Instance Information
  instanceName: string;

  // API Configuration
  apiUrl: string;
  domain: string;
  httpPort: string;

  // Feature Flags
  enableDebug: string;
  enableAnalytics: string;
  enableMaintenance: string;

  // Version Information
  version: string;
  buildTime: string;
  environment: string;

  // Custom Configuration
  customConfig: string;

  // Additional Settings
  maxUploadSize: string;
  sessionTimeout: string;
  defaultLanguage: string;

  // Feature URLs
  docsUrl: string;
  supportUrl: string;
  templatesUrl: string;

  // Security Settings
  csrfEnabled: string;
  httpsOnly: string;
}

// Extend Window interface to include our config
declare global {
  interface Window {
    REDIACC_CONFIG?: RediaccConfig;
  }
}

export type {
  GetTeamMachines_ResultSet1 as Machine,
  GetTeamRepositories_ResultSet1 as Repository,
  MachineAssignmentType,
  PluginContainer,
} from '@rediacc/shared/types';

// Modal types - only export what's actually used
export type { BaseModalProps } from './modal';

// Electron API types for desktop integration
export type {
  ElectronAPI,
  TerminalConnectParams,
  TerminalConnectResult,
  RsyncExecutorOptions,
  RsyncProgress,
  RsyncResult,
  RsyncChanges,
  ParsedProtocolUrl,
  UpdateInfo,
  UpdateProgress,
  SFTPConnectParams,
  SFTPConnectResult,
  SFTPFileInfo,
  SFTPSessionInfo,
  ContainerExecParams,
  ContainerLogsParams,
  ContainerStatsParams,
  ContainerSessionResult,
  VSCodeInfo,
  VSCodeInstallations,
  VSCodePreference,
  VSCodeLaunchOptions,
  VSCodeLaunchResult,
} from './electron';
export { isElectron, getElectronAPI } from './electron';
