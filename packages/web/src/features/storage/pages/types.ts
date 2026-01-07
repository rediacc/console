import type { QueueFunction } from '@rediacc/shared/types';

export interface StorageFunctionData {
  function: QueueFunction;
  params: Record<string, string | number | string[] | undefined>;
  priority: number;
  description: string;
  selectedMachine?: string;
}
