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
// Electron API types for desktop integration
export type {
  ContainerExecParams,
  ContainerLogsParams,
  ContainerSessionResult,
  ContainerStatsParams,
  ElectronAPI,
  ParsedProtocolUrl,
  RsyncChanges,
  RsyncExecutorOptions,
  RsyncProgress,
  RsyncResult,
  SFTPConnectParams,
  SFTPConnectResult,
  SFTPFileInfo,
  SFTPSessionInfo,
  TerminalConnectParams,
  TerminalConnectResult,
  UpdateInfo,
  UpdateProgress,
  VSCodeInfo,
  VSCodeInstallations,
  VSCodeLaunchOptions,
  VSCodeLaunchResult,
  VSCodePreference,
} from './electron';
export { getElectronAPI, isElectron } from './electron';
// Modal types - only export what's actually used
export type { BaseModalProps } from './modal';
