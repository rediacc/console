import type { Machine } from '@/types';

export type GroupByMode =
  | 'machine'
  | 'bridge'
  | 'team'
  | 'region'
  | 'repository'
  | 'status'
  | 'grand';

export interface MachineTableProps {
  teamFilter?: string | string[];
  showActions?: boolean;
  className?: string;
  onEditMachine?: (machine: Machine) => void;
  onFunctionsMachine?: (machine: Machine, functionName?: string) => void;
  onDeleteMachine?: (machine: Machine) => void;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  onRowClick?: (machine: Machine) => void;
  selectedMachine?: Machine | null;
}
