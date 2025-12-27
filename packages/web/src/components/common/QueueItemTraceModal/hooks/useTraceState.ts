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

/** Shape of command result in vault content */
interface CommandResult {
  command_output?: string;
  message?: string;
  status?: string;
  exit_code?: number;
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
  const [lastOutputStatus, setLastOutputStatus] = useState<string>(''); // Track the last status to detect completion
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

  // Handle accumulating console output
  // Note: These setState calls process incoming data, not derived state
  useEffect(() => {
    if (
      traceData?.responseVaultContent?.hasContent &&
      traceData.responseVaultContent.vaultContent
    ) {
      try {
        // vaultContent is always a string at this point (checked above)
        const vaultContent = JSON.parse(traceData.responseVaultContent.vaultContent) as Record<
          string,
          unknown
        >;

        if (vaultContent.status === 'completed') {
          // For completed status, replace accumulated output with final result
          let finalOutput = '';
          if (vaultContent.result && typeof vaultContent.result === 'string') {
            try {
              const result = JSON.parse(vaultContent.result);
              // Extract command output from the cleaned response structure
              finalOutput = result.command_output ?? '';

              // If no command output but we have a message, show it
              if (!finalOutput && result.message) {
                finalOutput = `[${result.status}] ${result.message}`;
                if (result.exit_code !== undefined) {
                  finalOutput += ` (exit code: ${result.exit_code})`;
                }
              }
            } catch {
              finalOutput = vaultContent.result;
            }
          }
          // eslint-disable-next-line react-hooks/set-state-in-effect -- Processing incoming data
          setAccumulatedOutput(finalOutput);
          setLastOutputStatus('completed');
        } else if (vaultContent.status === 'in_progress' && vaultContent.message) {
          // For in-progress updates, check if we should append or replace
          const newMessage = vaultContent.message as string;
          if (lastOutputStatus !== 'completed') {
            setAccumulatedOutput((currentOutput) => {
              // If the new message starts with the current content, only append the difference
              if (newMessage.startsWith(currentOutput)) {
                const newContent = newMessage.substring(currentOutput.length);
                return currentOutput + newContent;
              }
              // Otherwise, replace the entire content
              return newMessage;
            });
            setLastOutputStatus('in_progress');
          }
        } else if (!accumulatedOutput) {
          // Handle initial load for already completed tasks or other formats
          let initialOutput = '';
          if (vaultContent.result && typeof vaultContent.result === 'string') {
            try {
              const result = JSON.parse(vaultContent.result);
              // Extract command output from the cleaned response structure
              initialOutput = result.command_output ?? '';

              // If no command output but we have a message, show it
              if (!initialOutput && result.message) {
                initialOutput = `[${result.status}] ${result.message}`;
                if (result.exit_code !== undefined) {
                  initialOutput += ` (exit code: ${result.exit_code})`;
                }
              }
            } catch {
              initialOutput = vaultContent.result;
            }
          } else if (vaultContent.result && typeof vaultContent.result === 'object') {
            const result = vaultContent.result as CommandResult;
            // Same logic for object format
            initialOutput = result.command_output ?? '';
            if (!initialOutput && result.message) {
              initialOutput = `[${result.status}] ${result.message}`;
              if (result.exit_code !== undefined) {
                initialOutput += ` (exit code: ${result.exit_code})`;
              }
            }
          }
          if (initialOutput) {
            setAccumulatedOutput(initialOutput);
          }
        }
      } catch {
        // Error processing console output
      }
    }
  }, [traceData?.responseVaultContent, lastOutputStatus, accumulatedOutput]);

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
      setLastOutputStatus('');
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
    lastOutputStatus,
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
    setLastOutputStatus,
    setIsSimpleConsoleExpanded,
    setIsDetailedConsoleExpanded,
  };
};
