import type { Dayjs } from 'dayjs';
import type { QueueTraceLog } from '@rediacc/shared/types';

export interface QueueItemTraceModalProps {
  taskId: string | null;
  open: boolean;
  onCancel: () => void;
  onTaskStatusChange?: (status: string, taskId: string) => void;
}

export interface ConsoleOutputProps {
  content: string;
  theme: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  isEmpty?: boolean;
}

export interface SimplifiedStatus {
  status: string;
  color: 'default' | 'success' | 'error' | 'warning' | 'primary';
  icon: React.ReactNode;
}

export interface PriorityInfo {
  color: 'default';
  icon: React.ReactNode;
  label: string;
}

export type TaskStalenessLevel = 'none' | 'early' | 'stale' | 'critical';

export interface TraceState {
  lastTraceFetchTime: Dayjs | null;
  isMonitoring: boolean;
  activeKeys: string[];
  simpleMode: boolean;
  accumulatedOutput: string;
  lastOutputStatus: string;
  consoleProgress: number | null;
  progressMessage: string | null;
  isSimpleConsoleExpanded: boolean;
  isDetailedConsoleExpanded: boolean;
}

export interface TraceStateActions {
  setLastTraceFetchTime: (time: Dayjs | null) => void;
  setIsMonitoring: (monitoring: boolean) => void;
  setActiveKeys: (keys: string[]) => void;
  setSimpleMode: (simple: boolean) => void;
  setAccumulatedOutput: (output: string | ((prev: string) => string)) => void;
  setLastOutputStatus: (status: string) => void;
  setConsoleProgress: (progress: number | null) => void;
  setProgressMessage: (message: string | null) => void;
  setIsSimpleConsoleExpanded: (expanded: boolean) => void;
  setIsDetailedConsoleExpanded: (expanded: boolean) => void;
}

export interface TimelineViewProps {
  traceLogs: QueueTraceLog[];
}

export interface StatsPanelProps {
  queueDetails: any;
  totalDurationSeconds: number;
  processingDurationSeconds: number;
  isTaskStale: boolean;
}

export interface ResponseViewerProps {
  responseVaultContent: any;
  theme: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
}

export interface ActionButtonsProps {
  queueDetails: any;
  taskId: string | null;
  isCancelling: boolean;
  isRetrying: boolean;
  isTraceLoading: boolean;
  taskStaleness: TaskStalenessLevel;
  onCancel: () => void;
  onRetry: () => void;
  onRefresh: () => void;
  onClose: () => void;
  styles: any;
}
