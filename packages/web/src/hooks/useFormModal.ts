import { useState, useCallback } from 'react'

/**
 * Form modal modes
 */
export type FormModalMode = 'create' | 'edit' | 'vault'

/**
 * Form modal state interface
 */
export interface FormModalState<T = unknown> {
  /** Whether the modal is open */
  open: boolean
  /** Current mode */
  mode: FormModalMode
  /** Data for edit/vault modes */
  data: T | null
}

/**
 * Return type for useFormModal hook
 */
export interface UseFormModalReturn<T> {
  /** Current modal state */
  state: FormModalState<T>
  /** Open in create mode */
  openCreate: () => void
  /** Open in edit mode with existing data */
  openEdit: (data: T) => void
  /** Open in vault mode with existing data */
  openVault: (data: T) => void
  /** Close the modal */
  close: () => void
  /** Update data without changing mode */
  setData: (data: T | null) => void
  /** Check if modal is open */
  isOpen: boolean
  /** Get current mode */
  mode: FormModalMode
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
export function useFormModal<T = unknown>(
  defaultMode: FormModalMode = 'create'
): UseFormModalReturn<T> {
  const [state, setState] = useState<FormModalState<T>>({
    open: false,
    mode: defaultMode,
    data: null,
  })

  const openCreate = useCallback(() => {
    setState({
      open: true,
      mode: 'create',
      data: null,
    })
  }, [])

  const openEdit = useCallback((data: T) => {
    setState({
      open: true,
      mode: 'edit',
      data,
    })
  }, [])

  const openVault = useCallback((data: T) => {
    setState({
      open: true,
      mode: 'vault',
      data,
    })
  }, [])

  const close = useCallback(() => {
    setState({
      open: false,
      mode: defaultMode,
      data: null,
    })
  }, [defaultMode])

  const setData = useCallback((data: T | null) => {
    setState((prev) => ({
      ...prev,
      data,
    }))
  }, [])

  return {
    state,
    openCreate,
    openEdit,
    openVault,
    close,
    setData,
    isOpen: state.open,
    mode: state.mode,
  }
}

/**
 * Extended form modal with additional context
 */
export interface ExtendedFormModalState<T = unknown> extends FormModalState<T> {
  /** Preselected function for function selection modal */
  preselectedFunction?: string
  /** Creation context */
  creationContext?: 'credentials-only' | 'normal'
}

export interface UseExtendedFormModalReturn<T> extends UseFormModalReturn<T> {
  /** Open with preselected function */
  openWithFunction: (data: T, functionName: string) => void
  /** Get preselected function */
  preselectedFunction?: string
}

/**
 * Extended form modal hook with function selection support
 *
 * @example
 * const resourceModal = useExtendedFormModal<Resource>('normal')
 *
 * resourceModal.openWithFunction(resource, 'backup')
 */
export function useExtendedFormModal<T = unknown>(
  creationContext?: 'credentials-only' | 'normal'
): UseExtendedFormModalReturn<T> {
  const [state, setState] = useState<ExtendedFormModalState<T>>({
    open: false,
    mode: 'create',
    data: null,
    creationContext,
  })

  const openCreate = useCallback(() => {
    setState({
      open: true,
      mode: 'create',
      data: null,
      creationContext,
    })
  }, [creationContext])

  const openEdit = useCallback((data: T) => {
    setState({
      open: true,
      mode: 'edit',
      data,
      creationContext,
    })
  }, [creationContext])

  const openVault = useCallback((data: T) => {
    setState({
      open: true,
      mode: 'vault',
      data,
      creationContext,
    })
  }, [creationContext])

  const openWithFunction = useCallback(
    (data: T, functionName: string) => {
      setState({
        open: true,
        mode: 'edit',
        data,
        preselectedFunction: functionName,
        creationContext,
      })
    },
    [creationContext]
  )

  const close = useCallback(() => {
    setState({
      open: false,
      mode: 'create',
      data: null,
      creationContext,
    })
  }, [creationContext])

  const setData = useCallback((data: T | null) => {
    setState((prev) => ({
      ...prev,
      data,
    }))
  }, [])

  return {
    state,
    openCreate,
    openEdit,
    openVault,
    openWithFunction,
    close,
    setData,
    isOpen: state.open,
    mode: state.mode,
    preselectedFunction: state.preselectedFunction,
  }
}
