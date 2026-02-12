import type { TypedTFunction } from '@rediacc/shared/i18n/types';

export type { RcloneConfig, RcloneConfigFields } from '@rediacc/shared/queue-vault';

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
