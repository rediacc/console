import type { TypedTFunction } from '@rediacc/shared/i18n/types';

export type RcloneConfigFields = {
  [key: string]: string | number | boolean | Record<string, unknown> | undefined;
  type?: string;
};

export interface RcloneConfig {
  name: string;
  type: string;
  config: RcloneConfigFields;
}

export interface ImportStatus {
  name: string;
  status: 'pending' | 'success' | 'error' | 'skipped';
  message?: string;
  exists?: boolean;
  selected?: boolean;
}

export interface RcloneImportWizardProps {
  open: boolean;
  onClose: () => void;
  teamName: string;
  onImportComplete?: () => void;
}

export type WizardTranslator = TypedTFunction;
