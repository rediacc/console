import { useState, useCallback } from 'react'
import { ResourceType } from '@/components/common/UnifiedResourceModal'

export interface UnifiedModalState<T = Record<string, unknown>> {
  open: boolean
  resourceType: ResourceType
  mode: 'create' | 'edit' | 'vault'
  data?: Partial<T> | null
  preselectedFunction?: string
  creationContext?: 'credentials-only' | 'normal'
}

export interface UseUnifiedModalReturn<T> {
  modalState: UnifiedModalState<T>
  currentResource: T | null
  openModal: (
    mode: 'create' | 'edit' | 'vault',
    data?: Partial<T> | null,
    preselectedFunction?: string
  ) => void
  closeModal: () => void
  setCurrentResource: (resource: T | null) => void
}

export function useUnifiedModal<T extends Record<string, unknown> = Record<string, unknown>>(
  resourceType: ResourceType,
  initialCreationContext?: 'credentials-only' | 'normal'
): UseUnifiedModalReturn<T> {
  const [modalState, setModalState] = useState<UnifiedModalState<T>>({
    open: false,
    resourceType,
    mode: 'create',
    creationContext: initialCreationContext
  })

  const [currentResource, setCurrentResource] = useState<T | null>(null)

  const openModal = useCallback(
    (
      mode: 'create' | 'edit' | 'vault',
      data?: Partial<T> | null,
      preselectedFunction?: string
    ) => {
      setModalState({
        open: true,
        resourceType,
        mode,
        data,
        preselectedFunction,
        creationContext: initialCreationContext
      })
      if (data && mode !== 'create') {
        setCurrentResource(data as T)
      } else if (mode === 'create') {
        setCurrentResource(null)
      }
    },
    [resourceType, initialCreationContext]
  )

  const closeModal = useCallback(() => {
    setModalState({
      open: false,
      resourceType,
      mode: 'create',
      creationContext: initialCreationContext
    })
    setCurrentResource(null)
  }, [resourceType, initialCreationContext])

  return {
    modalState,
    currentResource,
    openModal,
    closeModal,
    setCurrentResource
  }
}
