import { useEffect, useRef, useState } from 'react';
import dayjs from 'dayjs';
import { extractMostRecentProgress, extractProgressMessage } from '@/platform';
import { queueMonitoringService } from '@/services/queueMonitoringService';
import type { TraceState, TraceStateActions } from '../types';

interface UseTraceStateProps {
  taskId: string | null;
  open: boolean;
  traceData: any;
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
  const [consoleProgress, setConsoleProgress] = useState<number | null>(null); // Progress percentage from console output
  const [progressMessage, setProgressMessage] = useState<string | null>(null); // Current progress message text
  const [isSimpleConsoleExpanded, setIsSimpleConsoleExpanded] = useState(false); // Console collapse state for simple mode
  const [isDetailedConsoleExpanded, setIsDetailedConsoleExpanded] = useState(false); // Console collapse state for detailed mode
  const consoleOutputRef = useRef<HTMLDivElement>(null);

  // Sync last fetch time when trace data or visibility changes
  useEffect(() => {
    if (traceData && open) {
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
  useEffect(() => {
    if (
      traceData?.responseVaultContent?.hasContent &&
      traceData.responseVaultContent.vaultContent
    ) {
      try {
        const vaultContent =
          typeof traceData.responseVaultContent.vaultContent === 'string'
            ? JSON.parse(traceData.responseVaultContent.vaultContent)
            : traceData.responseVaultContent.vaultContent || {};

        if (vaultContent.status === 'completed') {
          // For completed status, replace accumulated output with final result
          let finalOutput = '';
          if (vaultContent.result && typeof vaultContent.result === 'string') {
            try {
              const result = JSON.parse(vaultContent.result);
              // Extract command output from the cleaned response structure
              finalOutput = result.command_output || '';

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
          setAccumulatedOutput(finalOutput);
          setLastOutputStatus('completed');
        } else if (vaultContent.status === 'in_progress' && vaultContent.message) {
          // For in-progress updates, check if we should append or replace
          const newMessage = vaultContent.message;
          if (newMessage && lastOutputStatus !== 'completed') {
            setAccumulatedOutput((currentOutput) => {
              // If the new message starts with the current content, only append the difference
              if (newMessage.startsWith(currentOutput)) {
                const newContent = newMessage.substring(currentOutput.length);
                return currentOutput + newContent;
              } else {
                // Otherwise, replace the entire content
                return newMessage;
              }
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
              initialOutput = result.command_output || '';

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
            const result = vaultContent.result;
            // Same logic for object format
            initialOutput = result.command_output || '';
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

  // Extract progress percentage and message from console output
  useEffect(() => {
    const percentage = extractMostRecentProgress(accumulatedOutput);
    const message = extractProgressMessage(accumulatedOutput);

    setConsoleProgress(percentage);
    setProgressMessage(message);
  }, [accumulatedOutput]);

  // Reset states when modal opens with new taskId
  useEffect(() => {
    if (open && taskId) {
      setLastTraceFetchTime(null);
      // Check if this task is already being monitored
      setIsMonitoring(queueMonitoringService.isTaskMonitored(taskId));
      // Reset collapsed state and simple mode when opening modal
      setActiveKeys(['overview']);
      setSimpleMode(true); // Default to simple mode
      // Reset accumulated output when opening modal with new task
      setAccumulatedOutput('');
      setLastOutputStatus('');
      // Reset console progress, message, and collapse states
      setConsoleProgress(null);
      setProgressMessage(null);
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
    setConsoleProgress,
    setProgressMessage,
    setIsSimpleConsoleExpanded,
    setIsDetailedConsoleExpanded,
  };
};
