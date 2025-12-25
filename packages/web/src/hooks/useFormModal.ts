import { useCallback, useMemo, useState } from 'react';

/**
 * Form modal modes
 */
export type FormModalMode = 'create' | 'edit' | 'vault';

/**
 * Form modal state interface
 */
export interface FormModalState<T = unknown> {
  /** Whether the modal is open */
  open: boolean;
  /** Current mode */
  mode: FormModalMode;
  /** Data for edit/vault modes */
  data: T | null;
}

/**
 * Return type for useFormModal hook
 */
export interface UseFormModalReturn<T> {
  /** Current modal state */
  state: FormModalState<T>;
  /** Open in create mode */
  openCreate: () => void;
  /** Open in edit mode with existing data */
  openEdit: (data: T) => void;
  /** Open in vault mode with existing data */
  openVault: (data: T) => void;
  /** Close the modal */
  close: () => void;
  /** Update data without changing mode */
  setData: (data: T | null) => void;
  /** Check if modal is open */
  isOpen: boolean;
  /** Get current mode */
  mode: FormModalMode;
}

/**
 * Hook for managing form modal state with create/edit/vault modes
 *
 * @example
 * const cloneModal = useFormModal<CloneData>()
 *
 * // Open in different modes
 * cloneModal.openCreate()
 * cloneModal.openEdit(existingClone)
 * cloneModal.openVault(existingClone)
 *
 * // In modal component
 * <CloneModal
 *   open={cloneModal.isOpen}
 *   mode={cloneModal.mode}
 *   data={cloneModal.state.data}
 *   onCancel={cloneModal.close}
 * />
 */
/**
 * WARNING: Do not remove useMemo from return value!
 *
 * This hook returns a memoized object to prevent infinite render loops.
 * Without useMemo, a new object is created on every render, which causes
 * useEffect dependencies to trigger repeatedly, leading to "Maximum update
 * depth exceeded" errors.
 */
export function useFormModal<T = unknown>(
  defaultMode: FormModalMode = 'create'
): UseFormModalReturn<T> {
  const [state, setState] = useState<FormModalState<T>>({
    open: false,
    mode: defaultMode,
    data: null,
  });

  const openCreate = useCallback(() => {
    setState({
      open: true,
      mode: 'create',
      data: null,
    });
  }, []);

  const openEdit = useCallback((data: T) => {
    setState({
      open: true,
      mode: 'edit',
      data,
    });
  }, []);

  const openVault = useCallback((data: T) => {
    setState({
      open: true,
      mode: 'vault',
      data,
    });
  }, []);

  const close = useCallback(() => {
    setState({
      open: false,
      mode: defaultMode,
      data: null,
    });
  }, [defaultMode]);

  const setData = useCallback((data: T | null) => {
    setState((prev) => ({
      ...prev,
      data,
    }));
  }, []);

  return useMemo(
    () => ({
      state,
      openCreate,
      openEdit,
      openVault,
      close,
      setData,
      isOpen: state.open,
      mode: state.mode,
    }),
    [state, openCreate, openEdit, openVault, close, setData]
  );
}
