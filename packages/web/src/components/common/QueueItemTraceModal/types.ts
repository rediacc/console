import type { BaseModalProps } from '@/types';
import type {
  GetTeamQueueItems_ResultSet1,
  QueueTraceLog,
} from '@rediacc/shared/types';
import type { Dayjs } from 'dayjs';

export interface QueueItemTraceModalProps extends BaseModalProps {
  taskId: string | null;
  onTaskStatusChange?: (status: string, taskId: string) => void;
}

export type ConsoleViewMode = 'structured' | 'raw';

export interface ConsoleOutputProps {
  content: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  isEmpty?: boolean;
  viewMode: ConsoleViewMode;
}

export interface SimplifiedStatus {
  status: string;
  color: 'neutral' | 'success' | 'error' | 'warning' | 'primary';
  icon: React.ReactNode;
}

export interface PriorityInfo {
  color: 'neutral';
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
  setIsSimpleConsoleExpanded: (expanded: boolean) => void;
  setIsDetailedConsoleExpanded: (expanded: boolean) => void;
}

export interface TimelineViewProps {
  traceLogs: QueueTraceLog[];
}

export interface StatsPanelProps {
  queueDetails: GetTeamQueueItems_ResultSet1;
  totalDurationSeconds: number;
  processingDurationSeconds: number;
}

export interface ActionButtonsProps {
  queueDetails: GetTeamQueueItems_ResultSet1 | null | undefined;
  taskId: string | null;
  isCancelling: boolean;
  isRetrying: boolean;
  isTraceLoading: boolean;
  taskStaleness: TaskStalenessLevel;
  onCancel: () => void;
  onRetry: () => void;
  onRefresh: () => void;
  onClose: () => void;
}

export type TraceLog = QueueTraceLog;

/** QueueItemTraceData is an alias for the trace data structure */
export type { QueueTrace as QueueItemTraceData } from '@rediacc/shared/types';
