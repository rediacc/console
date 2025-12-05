import { useState, useCallback, useMemo } from 'react';

/**
 * Generic dialog state interface
 */
export interface DialogState<T = unknown> {
  /** Whether the dialog is open */
  open: boolean;
  /** Data passed to the dialog */
  data: T | null;
}

/**
 * Return type for useDialogState hook
 */
export interface UseDialogStateReturn<T> {
  /** Current dialog state */
  state: DialogState<T>;
  /** Open the dialog with optional data */
  open: (data?: T) => void;
  /** Close the dialog and clear data */
  close: () => void;
  /** Update data without changing open state */
  setData: (data: T | null) => void;
  /** Check if dialog is open */
  isOpen: boolean;
}

/**
 * Generic hook for managing dialog/modal state
 *
 * @example
 * const confirmDialog = useDialogState<{ id: string; name: string }>()
 *
 * // Open with data
 * confirmDialog.open({ id: '123', name: 'Item' })
 *
 * // In modal
 * <Modal open={confirmDialog.isOpen} onCancel={confirmDialog.close}>
 *   Are you sure you want to delete {confirmDialog.state.data?.name}?
 * </Modal>
 */
/**
 * WARNING: Do not remove useMemo from return value!
 *
 * This hook returns a memoized object to prevent infinite render loops.
 * Without useMemo, a new object is created on every render, which causes
 * useEffect dependencies to trigger repeatedly, leading to "Maximum update
 * depth exceeded" errors.
 *
 * See: UnifiedResourceModal's functionModal useEffect for an example of
 * code that depends on stable references from this hook.
 */
export function useDialogState<T = unknown>(): UseDialogStateReturn<T> {
  const [state, setState] = useState<DialogState<T>>({
    open: false,
    data: null,
  });

  const open = useCallback((data?: T) => {
    setState({
      open: true,
      data: data ?? null,
    });
  }, []);

  const close = useCallback(() => {
    setState({
      open: false,
      data: null,
    });
  }, []);

  const setData = useCallback((data: T | null) => {
    setState((prev) => ({
      ...prev,
      data,
    }));
  }, []);

  return useMemo(
    () => ({
      state,
      open,
      close,
      setData,
      isOpen: state.open,
    }),
    [state, open, close, setData]
  );
}

/**
 * Specialized dialog state for audit trace modals
 */
export interface TraceModalData {
  entityType: string;
  entityIdentifier: string;
  entityName?: string;
}

/**
 * Return type for useTraceModal hook with properly typed accessors
 */
export interface UseTraceModalReturn extends UseDialogStateReturn<TraceModalData> {
  /** Entity type (null when no data) */
  entityType: string | null;
  /** Entity identifier (null when no data) */
  entityIdentifier: string | null;
  /** Entity name (undefined when no data) */
  entityName: string | undefined;
}

/**
 * Hook for managing audit trace modal state
 *
 * @example
 * const auditTrace = useTraceModal()
 *
 * // Open trace modal
 * auditTrace.open({
 *   entityType: 'Machine',
 *   entityIdentifier: 'machine-01',
 *   entityName: 'Production Server'
 * })
 *
 * // In component
 * <AuditTraceModal
 *   open={auditTrace.isOpen}
 *   onCancel={auditTrace.close}
 *   entityType={auditTrace.entityType}
 *   entityIdentifier={auditTrace.entityIdentifier}
 *   entityName={auditTrace.entityName}
 * />
 */
export function useTraceModal(): UseTraceModalReturn {
  const dialogState = useDialogState<TraceModalData>();

  return useMemo(
    () => ({
      ...dialogState,
      entityType: dialogState.state.data?.entityType ?? null,
      entityIdentifier: dialogState.state.data?.entityIdentifier ?? null,
      entityName: dialogState.state.data?.entityName,
    }),
    [dialogState]
  );
}

/**
 * Specialized dialog state for queue trace modals
 */
export interface QueueTraceModalState {
  open: boolean;
  taskId: string | null;
  machineName?: string | null;
}

export interface UseQueueTraceModalReturn {
  state: QueueTraceModalState;
  open: (taskId: string, machineName?: string) => void;
  close: () => void;
  isOpen: boolean;
}

/**
 * Hook for managing queue trace modal state
 *
 * @example
 * const queueTrace = useQueueTraceModal()
 *
 * // After queue action
 * if (result.success && result.taskId) {
 *   queueTrace.open(result.taskId, machineName)
 * }
 *
 * // In component
 * <QueueItemTraceModal
 *   open={queueTrace.state.open}
 *   taskId={queueTrace.state.taskId}
 *   onCancel={queueTrace.close}
 * />
 */
export function useQueueTraceModal(): UseQueueTraceModalReturn {
  const [state, setState] = useState<QueueTraceModalState>({
    open: false,
    taskId: null,
    machineName: null,
  });

  const openModal = useCallback((taskId: string, machineName?: string) => {
    setState({
      open: true,
      taskId,
      machineName: machineName ?? null,
    });
  }, []);

  const close = useCallback(() => {
    setState({
      open: false,
      taskId: null,
      machineName: null,
    });
  }, []);

  return useMemo(
    () => ({
      state,
      open: openModal,
      close,
      isOpen: state.open,
    }),
    [state, openModal, close]
  );
}
