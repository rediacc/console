import { useEffect, useMemo, useRef, useState } from 'react';
import dayjs from 'dayjs';
import { extractMostRecentProgress, extractProgressMessage } from '@/platform';
import { queueMonitoringService } from '@/services/queue';
import type { QueueTrace } from '@rediacc/shared/types';
import type { TraceState, TraceStateActions } from '../types';

interface UseTraceStateProps {
  taskId: string | null;
  open: boolean;
  traceData: QueueTrace | null | undefined;
}

interface UseTraceStateReturn extends TraceState, TraceStateActions {
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
}

export const useTraceState = ({
  taskId,
  open,
  traceData,
}: UseTraceStateProps): UseTraceStateReturn => {
  const [lastTraceFetchTime, setLastTraceFetchTime] = useState<dayjs.Dayjs | null>(null);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [activeKeys, setActiveKeys] = useState<string[]>(['overview']); // Start with overview panel open
  const [simpleMode, setSimpleMode] = useState(true); // Default to simple mode
  const [accumulatedOutput, setAccumulatedOutput] = useState<string>(''); // Store accumulated console output
  const [isSimpleConsoleExpanded, setIsSimpleConsoleExpanded] = useState(false); // Console collapse state for simple mode
  const [isDetailedConsoleExpanded, setIsDetailedConsoleExpanded] = useState(false); // Console collapse state for detailed mode
  const consoleOutputRef = useRef<HTMLDivElement>(null);

  // Derive progress values from accumulated output (computed, not stored)
  const consoleProgress = useMemo(
    () => extractMostRecentProgress(accumulatedOutput),
    [accumulatedOutput]
  );
  const progressMessage = useMemo(
    () => extractProgressMessage(accumulatedOutput),
    [accumulatedOutput]
  );

  // Sync last fetch time when trace data or visibility changes
  // Note: This setState is intentional - we're tracking when data was fetched, not deriving state
  useEffect(() => {
    if (traceData && open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Tracking fetch timestamp, not derived state
      setLastTraceFetchTime(dayjs());
    }
  }, [traceData, open]);

  // Auto-scroll console output to bottom when output updates
  useEffect(() => {
    if (consoleOutputRef.current && accumulatedOutput) {
      consoleOutputRef.current.scrollTop = consoleOutputRef.current.scrollHeight;
    }
  }, [accumulatedOutput]);

  // Handle console output from response vault
  // The bridge sends plain text output directly in vaultContent
  useEffect(() => {
    if (
      traceData?.responseVaultContent?.hasContent &&
      traceData.responseVaultContent.vaultContent
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Syncing accumulated output with response data from API
      setAccumulatedOutput(traceData.responseVaultContent.vaultContent);
    }
  }, [traceData?.responseVaultContent]);

  // Reset states when modal opens with new taskId
  // Note: These setState calls are intentional initialization, not derived state
  useEffect(() => {
    if (open && taskId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional initialization when modal opens
      setLastTraceFetchTime(null);
      // Check if this task is already being monitored
      setIsMonitoring(queueMonitoringService.isTaskMonitored(taskId));
      // Reset collapsed state and simple mode when opening modal
      setActiveKeys(['overview']);
      setSimpleMode(true); // Default to simple mode
      // Reset accumulated output when opening modal with new task
      setAccumulatedOutput('');
      // Reset collapse states (consoleProgress/progressMessage are now derived via useMemo)
      setIsSimpleConsoleExpanded(false);
      setIsDetailedConsoleExpanded(false);
    }
  }, [taskId, open]);

  return {
    lastTraceFetchTime,
    isMonitoring,
    activeKeys,
    simpleMode,
    accumulatedOutput,
    consoleProgress,
    progressMessage,
    isSimpleConsoleExpanded,
    isDetailedConsoleExpanded,
    consoleOutputRef,
    setLastTraceFetchTime,
    setIsMonitoring,
    setActiveKeys,
    setSimpleMode,
    setAccumulatedOutput,
    setIsSimpleConsoleExpanded,
    setIsDetailedConsoleExpanded,
  };
};
