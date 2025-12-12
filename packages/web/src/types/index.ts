// Runtime configuration from nginx
export interface RediaccConfig {
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
  MachineAssignmentStatus,
  MachineAssignmentType,
  PluginContainer,
} from '@rediacc/shared/types';

// Modal types
export type {
  BaseModalProps,
  FormModalProps,
  SelectionModalProps,
  ConfirmationModalProps,
  DetailModalProps,
  ModalSize as ModalSizeEnum,
  ModalSizeValue,
  ModalConfig,
  ModalSizeRecommendation,
} from './modal';
export { ModalSize, MODAL_SIZE_RECOMMENDATIONS, getModalClassName } from './modal';

// Hook types
export type {
  UseModalReturn,
  UseDialogReturn,
  UseFormReturn,
  UsePaginationReturn,
  UseFiltersReturn,
  UseSelectionReturn,
  UseAsyncReturn,
} from './hooks';
