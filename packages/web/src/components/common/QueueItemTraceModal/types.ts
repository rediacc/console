import type { BaseModalProps } from '@/types';
import type {
  GetTeamQueueItems_ResultSet1,
  QueueTraceLog,
  QueueVaultSnapshot,
} from '@rediacc/shared/types';
import type { Dayjs } from 'dayjs';

export interface QueueItemTraceModalProps extends BaseModalProps {
  taskId: string | null;
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
  isTaskStale: boolean;
}

export interface ResponseViewerProps {
  responseVaultContent: QueueVaultSnapshot | null;
  theme: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
}

export interface ActionButtonStyles {
  buttonPrimary?: React.CSSProperties;
  buttonSecondary?: React.CSSProperties;
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
  styles: ActionButtonStyles;
}

export type TraceLog = QueueTraceLog;
export type TaskStaleness = TaskStalenessLevel;
