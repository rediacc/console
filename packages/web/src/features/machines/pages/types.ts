import type { QueueFunction } from '@/api/queries/queue';
import type { MachineFormValues as BaseMachineFormValues } from '@rediacc/shared/types';

// Extend shared type with UI-specific field for auto-setup option
export type MachineFormValues = BaseMachineFormValues & { autoSetup?: boolean };

export interface MachineFunctionParams {
  repository?: string;
  sourceType?: string;
  from?: string;
  [key: string]: string | number | boolean | undefined;
}

export interface MachineFunctionData {
  function: QueueFunction;
  params: MachineFunctionParams;
  priority: number;
  description: string;
}
