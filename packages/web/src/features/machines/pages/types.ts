import type { CreateMachineParams, QueueFunction } from '@rediacc/shared/types';

// Extend shared type with UI-specific field for auto-setup option
// Note: vaultContent and vaultVersion are already optional in CreateMachineParams
export interface MachineFormValues extends CreateMachineParams {
  autoSetup?: boolean;
}

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
